"""Gestión, conmutación y ejecución de proveedores LLM por tarea."""
import json
import queue
import threading
import time
import requests

import acciones
import config
from cerebro import _cortar, _respuesta_parcial, separar
import proveedores_cadenas as pc
from proveedores_validador import extraer_motivo, iniciar_validacion_segundo_plano

_enfriamientos = {}
enfriamientos = _enfriamientos
_aviso_respaldo_pendiente = False
_ultimo_proveedor = "Groq"
_claves_anteriores = {}


def forzar_utf8(texto):
    """Garantiza que el texto esté en UTF-8 correcto y corrige secuencias Latin-1."""
    if not texto or not isinstance(texto, str):
        return texto or ""
    if any(c in texto for c in ("Ã", "Â", "â")):
        try:
            return texto.encode("latin-1").decode("utf-8")
        except Exception:
            pass
    return texto


def _registrar(mensaje):
    print(f"[tiempo] {mensaje}", flush=True)


def marcar_enfriamiento(nombre, modelo=None, headers=None, motivo=None):
    """Pone a un modelo o proveedor en pausa durante 60 s o según Retry-After (máx 60 s)."""
    pc.marcar_enfriamiento(_enfriamientos, nombre, modelo, headers, motivo=motivo)


def proveedores_disponibles(tarea="charla"):
    """Devuelve la lista de proveedores configurados y disponibles para la tarea."""
    return pc.proveedores_disponibles(tarea, _enfriamientos, _claves_anteriores)


def _lanzar_reintento(tarea):
    pc.lanzar_reintento_segundo_plano(proveedores_disponibles, tarea)


def completar(mensajes, tarea="charla", timeout=20):
    global _aviso_respaldo_pendiente, _ultimo_proveedor
    candidatos = proveedores_disponibles(tarea)
    if not candidatos:
        _registrar("cerebro sin proveedores disponibles: modo emergencia local")
        _lanzar_reintento(tarea)
        return pc.respuesta_emergencia_local()

    ultimo_error = None
    for prov in candidatos:
        nombre = prov["nombre"]
        url = f"{prov['base_url'].rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {prov['clave']}", "Content-Type": "application/json"}
        modelos = prov.get("modelos_activos") or prov.get("modelos", [])

        for modelo in list(modelos):
            try:
                r = requests.post(url, headers=headers, json={"model": modelo, "messages": mensajes, "max_tokens": 500}, timeout=timeout)
                r.encoding = "utf-8"
                if r.status_code == 429:
                    mot = extraer_motivo(r, 429)
                    marcar_enfriamiento(nombre, modelo, r.headers, motivo=mot)
                    _registrar(f"cerebro 429 en {nombre} ({modelo}), pasando al siguiente modelo de la misma cuenta...")
                    continue
                if r.status_code == 404:
                    mot = extraer_motivo(r, 404)
                    marcar_enfriamiento(nombre, modelo, r.headers, motivo=mot)
                    _registrar(f"cerebro HTTP 404 en {nombre} ({modelo}): {mot}")
                    continue
                if r.status_code != 200:
                    _registrar(f"cerebro HTTP {r.status_code} en {nombre} ({modelo}): {r.text[:80]}")
                    continue
                try:
                    datos = r.json()
                except Exception:
                    datos = json.loads(r.content.decode("utf-8", errors="replace"))

                contenido = forzar_utf8(datos["choices"][0]["message"].get("content") or "")
                _registrar(f"cerebro proveedor={nombre} modelo={modelo} tarea={tarea}")
                _ultimo_proveedor = nombre
                return contenido
            except requests.exceptions.Timeout as ex:
                mot = f"timeout ({str(ex)[:60].strip()})"
                marcar_enfriamiento(nombre, modelo, motivo=mot)
                _registrar(f"cerebro timeout en {nombre} ({modelo}): {mot}")
            except Exception as e:
                ultimo_error = e
                _registrar(f"cerebro error en {nombre} ({modelo}): {e}")

        # Si agotó todos los modelos de este proveedor, registrar cambio de proveedor
        _registrar(f"cerebro agotados modelos en {nombre}, cambiando de proveedor")
        if nombre == "Groq" and _ultimo_proveedor == "Groq":
            _aviso_respaldo_pendiente = True

    _registrar("cerebro todos los proveedores fallaron: activando modo de emergencia local")
    _lanzar_reintento(tarea)
    return pc.respuesta_emergencia_local()


def _intentar_stream_proveedor(prov, modelos, mensajes, timeout_token, evento_cancelar, cola_salida):
    nombre = prov["nombre"]
    url = f"{prov['base_url'].rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {prov['clave']}", "Content-Type": "application/json"}
    t0 = time.time()
    lista_modelos = modelos if isinstance(modelos, list) else [modelos]

    for modelo in lista_modelos:
        if evento_cancelar.is_set():
            return
        try:
            r = requests.post(
                url,
                headers=headers,
                json={"model": modelo, "messages": mensajes, "stream": True, "max_tokens": 500},
                stream=True,
                timeout=(timeout_token, 6.0),
            )
            r.encoding = "utf-8"
            if r.status_code == 429:
                mot = extraer_motivo(r, 429)
                marcar_enfriamiento(nombre, modelo, r.headers, motivo=mot)
                _registrar(f"cerebro 429 en {nombre} ({modelo}), pasando al siguiente modelo de la misma cuenta...")
                continue
            if r.status_code == 404:
                mot = extraer_motivo(r, 404)
                marcar_enfriamiento(nombre, modelo, r.headers, motivo=mot)
                _registrar(f"cerebro HTTP 404 en {nombre} ({modelo}): {mot}")
                continue
            if r.status_code != 200:
                _registrar(f"cerebro HTTP {r.status_code} en {nombre} ({modelo})")
                continue

            primer_token = False
            for linea_raw in r.iter_lines(decode_unicode=False):
                if evento_cancelar.is_set():
                    try:
                        r.close()
                    except Exception:
                        pass
                    return

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
                delta = choices[0].get("delta", {}).get("content") or ""
                if not delta:
                    continue

                delta = forzar_utf8(delta)
                if not primer_token:
                    primer_token = True
                    t_token = time.time() - t0
                    cola_salida.put(("primer_token", nombre, modelo, t_token))

                cola_salida.put(("chunk", nombre, delta))

            if not primer_token:
                continue

            cola_salida.put(("fin", nombre, None))
            return
        except requests.exceptions.Timeout as ex:
            mot = f"timeout ({str(ex)[:60].strip()})"
            marcar_enfriamiento(nombre, modelo, motivo=mot)
            _registrar(f"cerebro timeout en {nombre} ({modelo}): {mot}")
            continue
        except Exception as ex:
            _registrar(f"cerebro fallo en {nombre} ({modelo}): {ex}")
            continue

    cola_salida.put(("error", nombre, RuntimeError(f"Todos los modelos de {nombre} fallaron")))


def completar_flujo(mensajes, al_frase, tarea="charla", timeout_paralelo=4.0):
    global _aviso_respaldo_pendiente, _ultimo_proveedor
    candidatos = proveedores_disponibles(tarea)
    if not candidatos:
        _registrar("cerebro sin proveedores para streaming: modo emergencia con voz")
        if callable(al_frase):
            al_frase(pc.FRASE_EMERGENCIA_LOCAL)
        _lanzar_reintento(tarea)
        return pc.respuesta_emergencia_local()

    idx = 0
    while idx < len(candidatos):
        p1 = candidatos[idx]
        m1 = p1.get("modelos_activos") or p1.get("modelos", [])
        p2 = candidatos[idx + 1] if (idx + 1 < len(candidatos)) else None
        m2 = (p2.get("modelos_activos") or p2.get("modelos", [])) if p2 else []

        cola = queue.Queue()
        cancelar_p1 = threading.Event()
        cancelar_p2 = threading.Event()

        hilo_p1 = threading.Thread(
            target=_intentar_stream_proveedor,
            args=(p1, m1, mensajes, 8.0, cancelar_p1, cola),
            daemon=True,
        )
        hilo_p1.start()

        # Esperar hasta timeout_paralelo por el primer token de P1
        ganador = None
        t_inicio = time.time()
        p2_lanzado = False

        while True:
            ahora = time.time()
            espera = max(0.05, timeout_paralelo - (ahora - t_inicio)) if not p2_lanzado else 0.1
            try:
                msg = cola.get(timeout=espera)
                tipo, prov_nom = msg[0], msg[1]
                if tipo == "primer_token":
                    ganador = p1 if prov_nom == p1["nombre"] else p2
                    mod_ganador = msg[2]
                    t_tok = msg[3]
                    if p2_lanzado:
                        perdedor = p2["nombre"] if ganador == p1 else p1["nombre"]
                        _registrar(f"cerebro ganador={ganador['nombre']} ({t_tok:.2f}s, superó a {perdedor})")
                        if ganador == p1:
                            cancelar_p2.set()
                        else:
                            cancelar_p1.set()
                    else:
                        _registrar(f"cerebro ganador={ganador['nombre']} modelo={mod_ganador} primer_token={t_tok:.2f}s")
                    break
                elif tipo == "error":
                    _registrar(f"cerebro {prov_nom} falló al iniciar: {msg[2]}")
                    if prov_nom == p1["nombre"] and not p2_lanzado:
                        # P1 falló antes de 4s: lanzar P2 de inmediato si existe
                        if p2:
                            p2_lanzado = True
                            hilo_p2 = threading.Thread(
                                target=_intentar_stream_proveedor,
                                args=(p2, m2, mensajes, 8.0, cancelar_p2, cola),
                                daemon=True,
                            )
                            hilo_p2.start()
                            continue
                        else:
                            break
                    elif p2_lanzado and prov_nom == p2["nombre"]:
                        pass
            except queue.Empty:
                if not p2_lanzado and p2:
                    p2_lanzado = True
                    _registrar(f"cerebro {p1['nombre']} tardó >{timeout_paralelo:.1f}s sin primer token; lanzando {p2['nombre']} en paralelo")
                    hilo_p2 = threading.Thread(
                        target=_intentar_stream_proveedor,
                        args=(p2, m2, mensajes, 8.0, cancelar_p2, cola),
                        daemon=True,
                    )
                    hilo_p2.start()
                elif (time.time() - t_inicio) > 16.0:
                    cancelar_p1.set()
                    cancelar_p2.set()
                    break

        if ganador is None:
            cancelar_p1.set()
            cancelar_p2.set()
            idx += 2 if p2_lanzado else 1
            continue

        # Consumir el stream del ganador
        nombre_g = ganador["nombre"]
        crudo, emitido = "", 0
        frases_emitidas = 0

        def emitir(f):
            nonlocal frases_emitidas
            global _aviso_respaldo_pendiente
            limpia = forzar_utf8(f)
            if not limpia:
                return
            if frases_emitidas == 0:
                if _aviso_respaldo_pendiente and nombre_g != "Groq":
                    _aviso_respaldo_pendiente = False
                    al_frase("Estoy usando mi cerebro de respaldo.")
                    frases_emitidas += 1
            al_frase(limpia)
            frases_emitidas += 1

        while True:
            try:
                item = cola.get(timeout=8.0)
                t_item, p_item = item[0], item[1]
                if p_item != nombre_g:
                    continue
                if t_item == "chunk":
                    chunk = item[2]
                    crudo += chunk
                    parcial = _respuesta_parcial(crudo)
                    if parcial is not None:
                        frases, emitido = _cortar(parcial, emitido)
                        for f in frases:
                            emitir(f)
                elif t_item in ("fin", "error"):
                    break
            except queue.Empty:
                break

        parcial = _respuesta_parcial(crudo)
        if parcial is None:
            txt = separar(crudo)[0]
            if txt:
                emitir(txt)
        else:
            frases, emitido = _cortar(parcial, emitido, final=True)
            for f in frases:
                emitir(f)

        if not crudo.strip():
            _registrar(f"cerebro {nombre_g} terminó con respuesta vacía")
            idx += 1
            continue

        _ultimo_proveedor = nombre_g
        return forzar_utf8(crudo)

    _registrar("cerebro todos los proveedores en streaming fallaron: activando modo de emergencia local con voz")
    if callable(al_frase):
        al_frase(pc.FRASE_EMERGENCIA_LOCAL)
    _lanzar_reintento(tarea)
    return pc.respuesta_emergencia_local()


def accion_estado_proveedores(app):
    def _tarea():
        texto_voz, texto_burbuja = pc.reporte_estado_proveedores(_enfriamientos)
        app.cola.put(("hablar_registro", (texto_voz, texto_burbuja)))
        print("[tiempo] Consulta de estado_proveedores completada.", flush=True)

    threading.Thread(target=_tarea, daemon=True).start()


def instalar(app):
    """Registra la acción estado_proveedores e inicia la validación de modelos remotos."""
    try:
        iniciar_validacion_segundo_plano()
    except Exception as e:
        _registrar(f"no se pudo iniciar validador de modelos: {e}")

    acciones.registrar(
        "estado_proveedores",
        lambda: accion_estado_proveedores(app),
        "informa el estado de los proveedores de IA (activos, enfriamiento o sin clave) y sus cadenas por tarea (úsala cuando pregunten 'cómo van los proveedores', 'estado de los proveedores', 'qué modelos están activos')",
    )
