"""Gestión y respaldo de proveedores LLM compatibles con OpenAI.

Orden: Groq -> Google Gemini -> OpenRouter -> Cerebras.
Salta claves vacías, enfría en caso de 429, fuerza UTF-8 contra caracteres rotos,
y conmuta automáticamente antes de la primera frase si hay fallo o pasan >8 s sin tokens.
"""
import json
import time
import requests

import config
from cerebro import _cortar, _respuesta_parcial, separar

_enfriamientos = {}
_aviso_respaldo_pendiente = False
_ultimo_proveedor = "Groq"
_ultima_clave_groq = None


def forzar_utf8(texto):
    """Garantiza que el texto esté en UTF-8 correcto y corrige secuencias Latin-1."""
    if not texto or not isinstance(texto, str):
        return texto or ""
    if "Ã" in texto or "Â" in texto or "â" in texto:
        try:
            return texto.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return texto


def _registrar(mensaje):
    print(f"[tiempo] {mensaje}", flush=True)


def marcar_enfriamiento(nombre, headers=None):
    """Pone a un proveedor en pausa durante 60 s o lo que indique Retry-After (máx 60 s)."""
    duracion = 60.0
    if headers:
        ra = headers.get("retry-after") or headers.get("Retry-After")
        if ra:
            try:
                duracion = min(60.0, max(5.0, float(ra)))
            except ValueError:
                duracion = 60.0
    _enfriamientos[nombre] = time.time() + duracion
    _registrar(f"enfriamiento proveedor={nombre} duracion={duracion:.0f}s")


def proveedores_disponibles():
    """Devuelve la lista de proveedores configurados, con clave y fuera de enfriamiento."""
    global _ultima_clave_groq
    ahora = time.time()
    disponibles = []

    clave_actual = getattr(config, "CLAVE", "")
    if clave_actual != _ultima_clave_groq:
        _ultima_clave_groq = clave_actual
        if "Groq" in _enfriamientos:
            _registrar("Groq: detectada nueva clave en config.py, reiniciando enfriamiento")
            _enfriamientos.pop("Groq", None)

    for p in config.PROVEEDORES:
        nombre = p["nombre"]
        if nombre == "Groq":
            p["clave"] = getattr(config, "CLAVE", "")
        elif nombre == "Google":
            p["clave"] = getattr(config, "CLAVE_GOOGLE", "")
        elif nombre == "OpenRouter":
            p["clave"] = getattr(config, "CLAVE_OPENROUTER", "")
        elif nombre == "Cerebras":
            p["clave"] = getattr(config, "CLAVE_CEREBRAS", "")

        clave = (p.get("clave") or "").strip()
        if not clave:
            _registrar(f"cerebro saltando proveedor={nombre} motivo=clave_vacia")
            continue

        if ahora < _enfriamientos.get(nombre, 0):
            restan = int(_enfriamientos[nombre] - ahora)
            _registrar(f"cerebro saltando proveedor={nombre} motivo=en_enfriamiento_por_cuota_faltan_{restan}s")
            continue

        disponibles.append(p)
    return disponibles


def completar(mensajes, timeout=20):
    """Llamada síncrona sin streaming con conmutación automática de respaldo."""
    global _aviso_respaldo_pendiente, _ultimo_proveedor
    candidatos = proveedores_disponibles()
    if not candidatos:
        raise RuntimeError("No hay proveedores de IA disponibles (claves vacías o en enfriamiento)")

    ultimo_error = None
    for prov in candidatos:
        nombre = prov["nombre"]
        url = f"{prov['base_url'].rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {prov['clave']}", "Content-Type": "application/json"}
        for modelo in list(prov.get("modelos", [])):
            try:
                r = requests.post(url, headers=headers, json={"model": modelo, "messages": mensajes}, timeout=timeout)
                r.encoding = "utf-8"
                if r.status_code == 429:
                    marcar_enfriamiento(nombre, r.headers)
                    raise RuntimeError(f"Cuota excedida (429) en {nombre}")
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code} en {nombre}: {r.text[:100]}")
                try:
                    datos = r.json()
                except Exception:
                    datos = json.loads(r.content.decode("utf-8", errors="replace"))

                contenido = forzar_utf8(datos["choices"][0]["message"].get("content") or "")
                _registrar(f"cerebro proveedor={nombre} modelo={modelo}")
                if modelo in prov["modelos"]:
                    prov["modelos"].remove(modelo)
                    prov["modelos"].insert(0, modelo)
                _ultimo_proveedor = nombre
                return contenido
            except Exception as e:
                ultimo_error = e
                _registrar(f"cerebro cambio proveedor anterior={nombre} motivo={e}")
                if nombre == "Groq" and _ultimo_proveedor == "Groq":
                    _aviso_respaldo_pendiente = True

    raise ultimo_error or RuntimeError("Todos los proveedores fallaron")


def completar_flujo(mensajes, al_frase, timeout_primer_token=8.0):
    """Streaming de respuesta con failover antes de hablar y forzado UTF-8."""
    global _aviso_respaldo_pendiente, _ultimo_proveedor
    candidatos = proveedores_disponibles()
    if not candidatos:
        raise RuntimeError("No hay proveedores de IA disponibles")

    ultimo_error = None
    for prov in candidatos:
        nombre = prov["nombre"]
        url = f"{prov['base_url'].rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {prov['clave']}", "Content-Type": "application/json"}

        for modelo in list(prov.get("modelos", [])):
            crudo, emitido = "", 0
            frases_emitidas = 0
            t0 = time.time()
            t_primero = {"token": None, "frase": None}

            def emitir(f):
                nonlocal frases_emitidas
                global _aviso_respaldo_pendiente
                limpia = forzar_utf8(f)
                if not limpia:
                    return
                if frases_emitidas == 0:
                    if t_primero["frase"] is None:
                        t_primero["frase"] = time.time() - t0
                    if _aviso_respaldo_pendiente and nombre != "Groq":
                        _aviso_respaldo_pendiente = False
                        al_frase("Estoy usando mi cerebro de respaldo.")
                        frases_emitidas += 1
                al_frase(limpia)
                frases_emitidas += 1

            MAX_TOTAL_SEGUNDOS = 25.0
            MAX_ENTRE_TOKENS = 6.0
            t_ultimo_token = t0

            try:
                r = requests.post(
                    url,
                    headers=headers,
                    json={"model": modelo, "messages": mensajes, "stream": True},
                    stream=True,
                    timeout=(timeout_primer_token, MAX_ENTRE_TOKENS),
                )
                r.encoding = "utf-8"
                if r.status_code == 429:
                    marcar_enfriamiento(nombre, r.headers)
                    raise RuntimeError(f"Cuota excedida (429) en {nombre}")
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code} en {nombre}: {r.text[:100]}")

                primer_token = False
                for linea_raw in r.iter_lines(decode_unicode=False):
                    ahora = time.time()
                    if (ahora - t0) > MAX_TOTAL_SEGUNDOS:
                        if frases_emitidas == 0:
                            raise TimeoutError(f"Tiempo total ({MAX_TOTAL_SEGUNDOS}s) excedido en {nombre}")
                        _registrar(f"cerebro tiempo total alcanzado ({MAX_TOTAL_SEGUNDOS}s); cerrando respuesta con naturalidad")
                        break

                    if primer_token and (ahora - t_ultimo_token) > MAX_ENTRE_TOKENS:
                        if frases_emitidas == 0:
                            raise TimeoutError(f"Pausa entre tokens ({MAX_ENTRE_TOKENS}s) excedida en {nombre}")
                        _registrar(f"cerebro pausa entre tokens ({MAX_ENTRE_TOKENS}s); cerrando respuesta con naturalidad")
                        break

                    if not primer_token and (ahora - t0) > timeout_primer_token:
                        raise TimeoutError(f"Más de {timeout_primer_token}s sin primer token en {nombre}")
                    if not linea_raw:
                        continue
                    try:
                        linea = linea_raw.decode("utf-8")
                    except UnicodeDecodeError:
                        linea = linea_raw.decode("latin-1", errors="replace")
                    linea = linea.strip()
                    if not linea.startswith("data:"):
                        continue
                    contenido = linea[5:].strip()
                    if contenido == "[DONE]":
                        break
                    try:
                        obj = json.loads(contenido)
                    except Exception:
                        continue

                    choices = obj.get("choices", [])
                    if not choices:
                        continue
                    parte = choices[0].get("delta", {}).get("content") or ""
                    if not parte:
                        continue

                    parte = forzar_utf8(parte)
                    ahora_token = time.time()
                    t_ultimo_token = ahora_token
                    if not primer_token:
                        primer_token = True
                        t_primero["token"] = ahora_token - t0

                    crudo += parte
                    parcial = _respuesta_parcial(crudo)
                    if parcial is not None:
                        frases, emitido = _cortar(parcial, emitido)
                        for f in frases:
                            emitir(f)

                if not primer_token:
                    raise TimeoutError(f"Stream sin tokens en {nombre}/{modelo}")

                parcial = _respuesta_parcial(crudo)
                if parcial is None:
                    txt = separar(crudo)[0]
                    if txt:
                        emitir(txt)
                else:
                    frases, emitido = _cortar(parcial, emitido, final=True)
                    for f in frases:
                        emitir(f)

                _registrar(f"cerebro proveedor={nombre} modelo={modelo} primer_token={t_primero['token']:.2f}s primera_frase={t_primero['frase']} total={time.time() - t0:.2f}s")
                if modelo in prov["modelos"]:
                    prov["modelos"].remove(modelo)
                    prov["modelos"].insert(0, modelo)
                _ultimo_proveedor = nombre
                return forzar_utf8(crudo)

            except Exception as e:
                ultimo_error = e
                if frases_emitidas > 0:
                    _registrar(f"cerebro excepción en stream tras empezar a hablar ({e}); cerrando frase con naturalidad")
                    parcial = _respuesta_parcial(crudo)
                    if parcial is None:
                        txt = separar(crudo)[0]
                        if txt:
                            emitir(txt)
                    else:
                        frases, emitido = _cortar(parcial, emitido, final=True)
                        for f in frases:
                            emitir(f)
                    return forzar_utf8(crudo)
                _registrar(f"cerebro cambio proveedor anterior={nombre} motivo={e}")
                if nombre == "Groq" and _ultimo_proveedor == "Groq":
                    _aviso_respaldo_pendiente = True

    raise ultimo_error or RuntimeError("Todos los proveedores fallaron en responder")
