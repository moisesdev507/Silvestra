"""Adaptadores de eventos remotos y autorización directa para sesiones LAN del dueño."""


def encolar_turno(puente, app, identity, texto, command):
    if not puente.reservar_turno(identity):
        return False
    payload = {
        "texto": texto,
        "device_id": identity["device_id"],
        "tipo_dispositivo": identity["tipo_dispositivo"],
        "identity": identity,
        "command": command.a_dict(),
    }
    try:
        app.cola.put(("texto_tablet", payload))
        return True
    except Exception:
        puente.reservar_turno(identity, cerrar=True)
        return False


def accion_autorizada_remota(app, identity, action):
    """Verifica si la sesión remota (LAN / HUD del dueño) tiene autorización para ejecutar la acción."""
    if not identity or not isinstance(identity, dict):
        return False

    tipo = str(identity.get("tipo_dispositivo") or "").lower()
    if tipo not in ("tablet_hud", "tablet", "pc_nucleo", "telefono_movil"):
        return False

    scopes = identity.get("scopes", [])
    scopes_str = {str(s).lower() for s in scopes}
    if not any(s in scopes_str for s in ("operation:request", "ui:control", "scope.operation_request", "scope.ui_control")):
        return False

    act_str = str(action or "").strip()
    if not act_str:
        return False

    nom_accion = act_str.split("|")[0].split()[0].strip().lower().replace(" ", "_")

    import acciones
    if nom_accion in acciones.ACCIONES or nom_accion in acciones.VIVAS or nom_accion in acciones.ESPECIALES:
        return True

    catalogo_permitido = {
        "escribir_archivo", "leer_archivo", "listar_archivos",
        "aprender_habilidad", "confirmar_habilidad", "poner_recordatorio",
        "listar_recordatorios", "cancelar_recordatorio", "recordar",
        "activar_hud", "abrir_hud", "activar_modo", "buscar",
        "abrir_navegador", "abrir_youtube", "abrir_calculadora",
    }
    if nom_accion in catalogo_permitido:
        return True

    try:
        import aprendiz_habilidades
        habs = aprendiz_habilidades.obtener_habilidades_aprobadas()
        if nom_accion in habs:
            return True
    except Exception:
        pass

    return False


def bloquear_accion_remota(app, identity, action):
    """Convierte la acción en solicitud pendiente si no está autorizada; la ejecuta si está autorizada."""
    if accion_autorizada_remota(app, identity, action):
        try:
            app.ejecutar(action)
            return True
        except Exception as e:
            print(f"[ecosistema] Error ejecutando acción remota autorizada: {e}", flush=True)
            return False

    try:
        bridge = app.pantalla_remota.puente
        request = bridge.command(identity, str(action), {"parametros": {}}, True)
        bridge.guardar_pendiente(identity, request)
        app.decir("La solicitud de acción quedó pendiente de aprobación autorizada.", emocion="calida")
    except Exception:
        app.decir("No pude validar la solicitud remota; no ejecuté ninguna acción.", emocion="calida")
    return False


def guardar_observacion(app, envelope):
    """Conserva procedencia y payload ya saneado como contexto, nunca ejecutable."""
    app.ultima_observacion_remota = envelope


def procesar(app, kind, payload):
    if kind == "ecosistema_observacion":
        return guardar_observacion(app, payload)
    url, code = payload
    app.pantalla_remota.mostrar_ventana_qr(url, code)
