"""Motor de streaming, validación de calidad y conmutación de proveedores LLM."""
import json
import queue
import threading
import time
import requests

from cerebro_parser import _cortar, _respuesta_parcial, separar, extraer_emocion_parcial
import calidad_respuesta as cr
import proveedores_cadenas as pc
from sesion_http import obtener_sesion
from proveedores_validador import extraer_motivo, desactivar_modelo, esta_desactivado
import proveedores_salud as _salud

LIMITE_RAPIDO = 1.2
TECHO_RAPIDO = 2.5
LIMITE_PRO = 4.0
TECHO_ESPERA = 5.0


def _s_fallo(nombre, modelo, categoria, motivo=""):
    try:
        _salud.registrar_fallo(nombre, modelo, categoria, motivo)
    except Exception:
        pass


def _s_ttft(nombre, modelo, valor):
    try:
        _salud.registrar_ttft(nombre, modelo, valor)
    except Exception:
        pass


def _s_exito(nombre, modelo):
    try:
        _salud.registrar_exito(nombre, modelo)
    except Exception:
        pass


def _intentar_stream_proveedor(prov, modelos, mensajes, timeout_token, evento_cancelar, cola_salida, marcar_enfriamiento_fn, registrar_fn, max_tokens=500):
    nombre = prov["nombre"]
    url = f"{prov['base_url'].rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {prov['clave']}", "Content-Type": "application/json"}
    t0 = time.time()
    lista_modelos = modelos if isinstance(modelos, list) else [modelos]

    for modelo in lista_modelos:
        if evento_cancelar.is_set():
            return
        if esta_desactivado(nombre, modelo):
            continue
        try:
            sesion = obtener_sesion()
            r = sesion.post(
                url,
                headers=headers,
                json={"model": modelo, "messages": mensajes, "stream": True, "max_tokens": max_tokens},
                stream=True,
                timeout=(timeout_token, 7.0),
            )
            r.encoding = "utf-8"
            if r.status_code == 429:
                mot = extraer_motivo(r, 429)
                marcar_enfriamiento_fn(nombre, modelo, r.headers, motivo=mot)
                _s_fallo(nombre, modelo, "429", mot)
                registrar_fn(f"cerebro 429 en {nombre} ({modelo}), pasando al siguiente modelo de la misma cuenta...")
                continue
            if r.status_code == 404:
                mot = extraer_motivo(r, 404)
                marcar_enfriamiento_fn(nombre, modelo, r.headers, motivo=mot)
                desactivar_modelo(nombre, modelo)
                _s_fallo(nombre, modelo, "404", mot)
                registrar_fn(f"cerebro HTTP 404 en {nombre} ({modelo}): {mot} (desactivado)")
                continue
            if r.status_code != 200:
                _s_fallo(nombre, modelo, "http", f"HTTP {r.status_code}")
                registrar_fn(f"cerebro HTTP {r.status_code} en {nombre} ({modelo})")
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

                if not primer_token:
                    primer_token = True
                    t_token = time.time() - t0
                    _s_ttft(nombre, modelo, t_token)
                    cola_salida.put(("primer_token", nombre, modelo, t_token))

                cola_salida.put(("chunk", nombre, delta))

            if not primer_token:
                continue

            cola_salida.put(("fin", nombre, None))
            return
        except requests.exceptions.Timeout as ex:
            mot = f"timeout ({str(ex)[:60].strip()})"
            marcar_enfriamiento_fn(nombre, modelo, motivo=mot)
            _s_fallo(nombre, modelo, "timeout", mot)
            registrar_fn(f"cerebro timeout en {nombre} ({modelo}): {mot}")
            continue
        except Exception as ex:
            _s_fallo(nombre, modelo, "excepcion", str(ex)[:80])
            registrar_fn(f"cerebro fallo en {nombre} ({modelo}): {ex}")
            continue

    cola_salida.put(("error", nombre, RuntimeError(f"Todos los modelos de {nombre} fallaron")))


def _lanzar(prov, modelos, mensajes, limite, cola, marcar_fn, registrar_fn, max_tokens):
    """Arranca el intento de un proveedor y devuelve su evento de cancelación."""
    cancelar = threading.Event()
    threading.Thread(
        target=_intentar_stream_proveedor,
        args=(prov, modelos, mensajes, limite, cancelar, cola, marcar_fn, registrar_fn, max_tokens),
        daemon=True,
    ).start()
    return cancelar


def _esperar_ganador(cola, nombres, limite, on_primer_token, registrar_fn):
    """Espera el primer token de cualquiera de los proveedores del lote (hedging)."""
    t_inicio = time.time()
    while time.time() - t_inicio < limite:
        try:
            msg = cola.get(timeout=0.2)
        except queue.Empty:
            continue
        tipo, prov_nom = msg[0], msg[1]
        if prov_nom not in nombres:
            continue
        if tipo == "primer_token":
            if callable(on_primer_token):
                try:
                    on_primer_token()
                except Exception:
                    pass
            registrar_fn(f"cerebro ganador={prov_nom} modelo={msg[2]} primer_token={msg[3]:.2f}s")
            return prov_nom, msg[2]
        if tipo == "error":
            registrar_fn(f"cerebro {prov_nom} falló: {msg[2]}")
            nombres.discard(prov_nom)
            if not nombres:
                return None, None
    return None, None


def completar_flujo(mensajes, al_frase, tarea, candidatos, forzar_utf8_fn, marcar_enfriamiento_fn, registrar_fn, lanzar_reintento_fn, timeout_espera=1.2, on_primer_token=None, on_emocion=None, carril="rapido", max_tokens=500):
    """Streaming con hedging top-2, control de calidad y fallback secuencial."""
    if not candidatos:
        registrar_fn("cerebro sin proveedores para streaming: modo emergencia con voz")
        if callable(al_frase):
            al_frase(pc.FRASE_EMERGENCIA_LOCAL)
        lanzar_reintento_fn(tarea)
        return pc.respuesta_emergencia_local(), "Local", "emergencia"

    limite_espera = LIMITE_PRO if carril == "pro" else min(float(timeout_espera), TECHO_RAPIDO)
    limite_espera = min(limite_espera, TECHO_ESPERA)

    idx = 0
    tiempo_perdido_fallos = 0.0
    while idx < len(candidatos):
        # Hedging: los dos primeros proveedores compiten en paralelo.
        if idx == 0 and len(candidatos) > 1:
            lote = candidatos[idx:idx + 2]
        else:
            lote = candidatos[idx:idx + 1]

        cola = queue.Queue()
        cancelaciones = []
        nombres = []
        for p in lote:
            m_list = p.get("modelos_activos") or p.get("modelos", [])
            cancelaciones.append(
                _lanzar(p, m_list, mensajes, limite_espera, cola, marcar_enfriamiento_fn, registrar_fn, max_tokens)
            )
            nombres.append(p["nombre"])
        if len(lote) > 1:
            registrar_fn(f"cerebro hedge top-2: {', '.join(nombres)}")

        t_inicio = time.time()
        nombre_p, mod_activo = _esperar_ganador(
            cola, set(nombres), limite_espera, on_primer_token, registrar_fn
        )

        if nombre_p is None:
            for cancelar in cancelaciones:
                cancelar.set()
            dt_perdido = time.time() - t_inicio
            tiempo_perdido_fallos += dt_perdido
            registrar_fn(f"cerebro lote {nombres} superó tiempo de espera ({limite_espera:.1f}s) sin responder")
            for n_fallido in nombres:
                _s_fallo(n_fallido, None, "timeout", "sin primer token")
            idx += len(lote)
            continue

        # Cancelar al perdedor del hedge en cuanto hay ganador.
        for cancelar, nombre in zip(cancelaciones, nombres):
            if nombre != nombre_p:
                cancelar.set()

        # Consumir el stream del proveedor ganador y aplicar control de calidad
        crudo, emitido = "", 0
        frases_emitidas = 0
        descartado_por_calidad = False
        emo_detectada = None

        while True:
            try:
                item = cola.get(timeout=8.0)
                t_item, p_item = item[0], item[1]
                if p_item != nombre_p:
                    continue
                if t_item == "chunk":
                    chunk = item[2]
                    crudo += chunk
                    if emo_detectada is None:
                        emo_detectada = extraer_emocion_parcial(crudo)
                        if emo_detectada:
                            registrar_fn(f"cerebro emocion_temprana={emo_detectada}")
                            if callable(on_emocion):
                                try:
                                    on_emocion(emo_detectada)
                                except Exception:
                                    pass
                    parcial = _respuesta_parcial(crudo)
                    if parcial is not None:
                        frases, emitido = _cortar(parcial, emitido)
                        for f in frases:
                            f_limpia = forzar_utf8_fn(f)
                            if not f_limpia:
                                continue
                            # Validar lingüísticamente la primera frase antes de sintetizar voz
                            if frases_emitidas == 0:
                                ok_f, mot_f = cr.analizar_calidad_texto(f_limpia, contexto_windows=mensajes)
                                if not ok_f:
                                    registrar_fn(f"filtro_calidad frase rechazada en {nombre_p} ({mod_activo}): '{f_limpia}' motivo={mot_f}. Descartando proveedor.")
                                    _s_fallo(nombre_p, mod_activo, "calidad", mot_f)
                                    cancelar.set()
                                    descartado_por_calidad = True
                                    break
                            if callable(al_frase):
                                item_envio = (f_limpia, emo_detectada) if emo_detectada else f_limpia
                                al_frase(item_envio)
                            frases_emitidas += 1
                    if descartado_por_calidad:
                        break
                elif t_item in ("fin", "error"):
                    break
            except queue.Empty:
                break

        if descartado_por_calidad:
            idx += len(lote)
            continue

        # Emitir fragmentos finales pendientes
        parcial = _respuesta_parcial(crudo)
        if parcial is None:
            txt, _, _, emo_fin = separar(crudo)
            if txt and frases_emitidas == 0:
                ok_txt, mot_txt = cr.analizar_calidad_texto(txt, contexto_windows=mensajes)
                if ok_txt and callable(al_frase):
                    emo_usar = emo_detectada or emo_fin
                    item_envio = (forzar_utf8_fn(txt), emo_usar) if emo_usar else forzar_utf8_fn(txt)
                    al_frase(item_envio)
                    frases_emitidas += 1
                elif not ok_txt:
                    registrar_fn(f"filtro_calidad texto final rechazado en {nombre_p} ({mod_activo}): '{txt}' motivo={mot_txt}")
                    _s_fallo(nombre_p, mod_activo, "calidad", mot_txt)
                    idx += len(lote)
                    continue
        else:
            frases, emitido = _cortar(parcial, emitido, final=True)
            for f in frases:
                f_limpia = forzar_utf8_fn(f)
                if not f_limpia:
                    continue
                if frases_emitidas == 0:
                    ok_f, mot_f = cr.analizar_calidad_texto(f_limpia, contexto_windows=mensajes)
                    if not ok_f:
                        registrar_fn(f"filtro_calidad frase final rechazada en {nombre_p} ({mod_activo}): '{f_limpia}' motivo={mot_f}")
                        _s_fallo(nombre_p, mod_activo, "calidad", mot_f)
                        descartado_por_calidad = True
                        break
                if callable(al_frase):
                    item_envio = (f_limpia, emo_detectada) if emo_detectada else f_limpia
                    al_frase(item_envio)
                frases_emitidas += 1

        if descartado_por_calidad:
            idx += len(lote)
            continue

        texto_limpio = forzar_utf8_fn(crudo)
        resp_final, _, _, _ = separar(texto_limpio)
        if not resp_final.strip():
            registrar_fn(f"cerebro {nombre_p} terminó con respuesta vacía")
            _s_fallo(nombre_p, mod_activo, "vacia", "respuesta vacía")
            idx += len(lote)
            continue

        # Validación de la respuesta completa
        ok_resp, mot_resp = cr.analizar_calidad_texto(resp_final, contexto_windows=mensajes)
        if not ok_resp:
            registrar_fn(f"filtro_calidad respuesta completa rechazada en {nombre_p} ({mod_activo}): '{resp_final[:60]}' motivo={mot_resp}")
            _s_fallo(nombre_p, mod_activo, "calidad", mot_resp)
            idx += len(lote)
            continue

        _s_exito(nombre_p, mod_activo)

        # Registro explícito del proveedor y modelo final
        if tiempo_perdido_fallos > 0:
            registrar_fn(f"tiempo_perdido_fallos={tiempo_perdido_fallos:.2f}s")
        if tarea == "fondo":
            registrar_fn(f"tarea_fondo proveedor={nombre_p} modelo={mod_activo}")
        else:
            registrar_fn(f"respuesta proveedor={nombre_p} modelo={mod_activo}")

        return texto_limpio, nombre_p, mod_activo

    registrar_fn("cerebro todos los proveedores en streaming fallaron o fueron rechazados: activando modo emergencia con voz")
    if callable(al_frase):
        al_frase(pc.FRASE_EMERGENCIA_LOCAL)
    lanzar_reintento_fn(tarea)
    return pc.respuesta_emergencia_local(), "Local", "emergencia"
