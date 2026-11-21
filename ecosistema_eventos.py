"""Adaptadores de eventos remotos; no ejecutan acciones directamente."""


def encolar_turno(puente, app, identity, texto, command):
    if not puente.reservar_turno(identity): return False
    payload = {"texto": texto, "device_id": identity["device_id"],
        "tipo_dispositivo": identity["tipo_dispositivo"], "identity": identity,
        "command": command.a_dict()}
    try: app.cola.put(("texto_tablet", payload)); return True
    except Exception:
        puente.reservar_turno(identity, cerrar=True); return False


def bloquear_accion_remota(app, identity, action):
    """Convierte la acción sugerida en solicitud pendiente de aprobación."""
    try:
        bridge = app.pantalla_remota.puente
        request = bridge.command(identity, str(action), {"parametros": {}}, True)
        bridge.guardar_pendiente(identity, request)
        app.decir("La solicitud de acción quedó pendiente de aprobación autorizada.", emocion="calida")
    except Exception:
        app.decir("No pude validar la solicitud remota; no ejecuté ninguna acción.", emocion="calida")


def guardar_observacion(app, envelope):
    """Conserva procedencia y payload ya saneado como contexto, nunca ejecutable."""
    app.ultima_observacion_remota = envelope


def procesar(app, kind, payload):
    if kind == "ecosistema_observacion":
        return guardar_observacion(app, payload)
    url, code = payload
    app.pantalla_remota.mostrar_ventana_qr(url, code)
