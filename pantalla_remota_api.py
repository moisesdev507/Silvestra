"""Endpoints POST seguros para el HUD Jarvis de la tablet (consola y acciones rápidas)."""
import json
import threading

# Acciones permitidas desde la tablet: nombre_accion -> descripción breve
ACCIONES_PERMITIDAS = {
    "tablet_modo_privado": "Activa modo privado en la tablet",
    "tablet_modo_normal": "Activa modo normal en la tablet",
    "crear_respaldo": "Genera respaldo de datos del usuario",
    "ocultar_tarjeta": "Limpia la tarjeta principal del HUD",
    "toggle_solo_dueno": "Alterna modo exclusivo solo dueño",
    "reforzar_mi_voz": "Refuerza el banco biométrico de voz",
    "reforzar_voz": "Refuerza el banco biométrico de voz",
}

MAX_COMANDO_CHARS = 500


def _json_respuesta(handler, codigo, datos):
    """Envía una respuesta JSON al cliente HTTP."""
    cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
    handler.send_response(codigo)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(cuerpo)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    try:
        handler.wfile.write(cuerpo)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
        pass


def _leer_body_json(handler):
    """Lee y parsea el cuerpo JSON de un POST. Retorna dict o None."""
    try:
        largo = int(handler.headers.get("Content-Length", 0))
        if largo <= 0 or largo > 8192:
            return None
        raw = handler.rfile.read(largo)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def manejar_options(handler):
    """Responde preflight CORS para POST desde la tablet."""
    handler.send_response(204)
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()


def manejar_comando(handler, app, gestor):
    """POST /api/panel/comando — envía texto al flujo normal de Silvestra."""
    body = _leer_body_json(handler)
    if not body or "texto" not in body:
        _json_respuesta(handler, 400, {"error": "Se requiere campo 'texto' en el cuerpo JSON."})
        return

    texto = str(body["texto"]).strip()
    if not texto:
        _json_respuesta(handler, 400, {"error": "El campo 'texto' no puede estar vacío."})
        return
    if len(texto) > MAX_COMANDO_CHARS:
        _json_respuesta(handler, 400, {"error": f"Texto demasiado largo (máx {MAX_COMANDO_CHARS} chars)."})
        return

    # Encolar de forma thread-safe al bucle de eventos de Silvestra
    try:
        app.cola.put(("texto_tablet", texto))
        if gestor:
            gestor.registrar_evento(f"Cmd tablet: {texto[:30]}")
        _json_respuesta(handler, 200, {"ok": True, "encolado": texto[:60]})
    except Exception as e:
        _json_respuesta(handler, 500, {"error": f"Error interno al encolar: {e}"})


def manejar_accion(handler, app, gestor):
    """POST /api/panel/accion — ejecuta acción de la lista blanca."""
    body = _leer_body_json(handler)
    if not body or "accion" not in body:
        _json_respuesta(handler, 400, {"error": "Se requiere campo 'accion' en el cuerpo JSON."})
        return

    nombre = str(body.get("accion", "")).strip()
    if nombre not in ACCIONES_PERMITIDAS:
        lista = list(ACCIONES_PERMITIDAS.keys())
        _json_respuesta(handler, 400, {"error": f"Acción no permitida. Válidas: {lista}"})
        return

    def _ejecutar():
        try:
            if nombre == "ocultar_tarjeta":
                if gestor:
                    gestor.tarjeta_principal = "SILVESTRA VIRTUAL INTERFACE // SISTEMA OPERATIVO"
                    gestor.registrar_evento("Tarjeta principal reiniciada")
                return
            # Resto de acciones: delegar al gestor de acciones registrado
            import acciones as _acc
            ok, msg = _acc.ejecutar(nombre)
            if gestor:
                estado_txt = "OK" if ok else "ERROR"
                gestor.registrar_evento(f"Acción {nombre}: {estado_txt}")
        except Exception as ex:
            print(f"[pantalla_remota_api] Error ejecutando {nombre}: {ex}", flush=True)

    hilo = threading.Thread(target=_ejecutar, daemon=True, name=f"AccionTablet-{nombre}")
    hilo.start()

    if gestor:
        gestor.registrar_evento(f"Acción solicitada: {nombre}")
    _json_respuesta(handler, 200, {"ok": True, "accion": nombre, "desc": ACCIONES_PERMITIDAS[nombre]})


def manejar_biometria(handler, app, gestor, ruta=None):
    """POST /api/panel/biometria, /api/panel/solo_dueno o /api/panel/reforzar_voz."""
    import pantalla_biometria
    body = _leer_body_json(handler) or {}
    accion = str(body.get("accion", "")).strip().lower()
    ruta_str = str(ruta or "").lower()

    if "solo_dueno" in ruta_str or accion in ("toggle_solo_dueno", "solo_dueno"):
        activar = body.get("activar")
        bio = pantalla_biometria.toggle_solo_dueno(app, activar=activar)
        if gestor:
            gestor.registrar_evento(f"Solo Dueño: {'ON' if bio['solo_dueno'] else 'OFF'}")
        _json_respuesta(handler, 200, {"ok": True, "accion": "solo_dueno", "biometria": bio})
        return

    if "reforzar_voz" in ruta_str or accion in ("reforzar_voz", "reforzar_mi_voz"):
        ok, msg, bio = pantalla_biometria.disparar_reforzar_voz(app)
        if gestor:
            gestor.registrar_evento("Refuerzo voz solicitado")
        codigo = 200 if ok else 429
        _json_respuesta(handler, codigo, {"ok": ok, "mensaje": msg, "biometria": bio})
        return

    # Consulta de estado biométrico
    bio = pantalla_biometria.obtener_estado_biometria(app)
    _json_respuesta(handler, 200, {"ok": True, "biometria": bio})
