"""Módulo de gestión de modos operativos compuestos para Silvestra.

Modos soportados:
- normal: Comportamiento estándar equilibrado.
- programacion: Solo dueño activado, apertura de VS Code y respuestas técnicas/concisas.
- estudio: Solo dueño activado, volumen atenuado (~45%) y ayuda clara paso a paso.
- noche: Solo dueño activado, volumen bajo (~25%) y tono nocturno calmado.
"""
import os
import threading
import unicodedata

MODOS_VALIDOS = ("normal", "programacion", "estudio", "noche")

MODOS_CONFIG = {
    "normal": {
        "modo": "normal",
        "etiqueta": "Normal",
        "solo_dueno": None,
        "volumen": 60,
        "directiva_prompt": "",
    },
    "programacion": {
        "modo": "programacion",
        "etiqueta": "Programación",
        "solo_dueno": True,
        "volumen": None,
        "directiva_prompt": "MODO PROGRAMACIÓN ACTIVO: Da respuestas técnicas, concisas y orientadas a código limpio sin rodeos.",
    },
    "estudio": {
        "modo": "estudio",
        "etiqueta": "Estudio",
        "solo_dueno": True,
        "volumen": 45,
        "directiva_prompt": "MODO ESTUDIO ACTIVO: Brinda ayuda clara paso a paso para estudiar y practicar sin distraer ni alargarte de más.",
    },
    "noche": {
        "modo": "noche",
        "etiqueta": "Noche",
        "solo_dueno": True,
        "volumen": 25,
        "directiva_prompt": "MODO NOCHE ACTIVO: Habla con tono calmado, muy breve y de bajo perfil nocturno.",
    },
}

ALIAS_MODOS = {
    "normal": "normal",
    "estandar": "normal",
    "defecto": "normal",
    "programacion": "programacion",
    "programar": "programacion",
    "codigo": "programacion",
    "dev": "programacion",
    "desarrollo": "programacion",
    "estudio": "estudio",
    "estudiar": "estudio",
    "enfoque": "estudio",
    "concentracion": "estudio",
    "pomodoro": "estudio",
    "noche": "noche",
    "nocturno": "noche",
    "descanso": "noche",
    "dormir": "noche",
}


def normalizar_texto(texto):
    """Elimina tildes y caracteres especiales para comparaciones seguras."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFD", str(texto).strip().lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def normalizar_modo(texto):
    """Normaliza un nombre o alias de modo a su identificador canónico."""
    limpio = normalizar_texto(texto)
    if not limpio:
        return None
    # 1. Coincidencia directa o por alias
    if limpio in ALIAS_MODOS:
        return ALIAS_MODOS[limpio]
    # 2. Búsqueda de palabra clave en frases (ej. "modo noche", "ponte en modo programar")
    palabras = limpio.split()
    for p in palabras:
        if p in ALIAS_MODOS:
            return ALIAS_MODOS[p]
    return None


def obtener_modo_activo(app=None):
    """Retorna el modo activo actual (desde app o estado.json, fallback 'normal')."""
    if app and hasattr(app, "modo_activo") and app.modo_activo:
        m = normalizar_modo(app.modo_activo)
        if m in MODOS_VALIDOS:
            return m
    try:
        import estado
        d = estado.cargar()
        m = normalizar_modo(d.get("modo_activo", "normal"))
        if m in MODOS_VALIDOS:
            return m
    except Exception:
        pass
    return "normal"


def directiva_prompt_modo(app=None):
    """Devuelve la directiva corta de prompt para el modo actual (vacía en 'normal')."""
    m = obtener_modo_activo(app)
    return MODOS_CONFIG.get(m, {}).get("directiva_prompt", "")


def _ajustar_volumen_pc(pct_objetivo):
    """Ajusta aproximadamente el volumen de la PC mediante pulsaciones virtuales."""
    try:
        import control_pc
        # Baja a cero y luego sube hasta el porcentaje deseado (~2% por pulsación)
        control_pc.pulsar_tecla_vk(control_pc.VK_VOLUME_DOWN, veces=50, intervalo=0.01)
        subidas = max(0, min(50, int(pct_objetivo / 2)))
        if subidas > 0:
            control_pc.pulsar_tecla_vk(control_pc.VK_VOLUME_UP, veces=subidas, intervalo=0.01)
    except Exception as e:
        print(f"[modos_sistema] Aviso ajustando volumen a {pct_objetivo}%: {e}", flush=True)


def _abrir_vscode_seguro(app):
    """Intenta abrir VS Code de forma segura sin bloquear ni crashear."""
    try:
        import control_pc
        ok = control_pc.abrir_programa(app, "vscode", hablar=False)
        if ok:
            print("[modo] vscode_lanzado=True", flush=True)
        else:
            print("[modo] vscode_error=no_permitido_o_no_encontrado", flush=True)
    except Exception as e:
        print(f"[modo] vscode_error={e}", flush=True)


def activar_modo(app, modo, origen="voz"):
    """Activa un modo del sistema, ejecuta sus rutinas y persiste el cambio."""
    modo_can = normalizar_modo(modo)
    if not modo_can or modo_can not in MODOS_CONFIG:
        return False, f"El modo '{modo}' no es válido. Usa: normal, programación, estudio o noche.", None

    cfg = MODOS_CONFIG[modo_can]

    # 1. Persistencia atómica en estado.json
    try:
        import estado
        d = estado.cargar()
        d["modo_activo"] = modo_can
        estado.guardar(d)
    except Exception as e:
        print(f"[modos_sistema] Error guardando estado.json: {e}", flush=True)

    # 2. Actualizar estado en memoria de app
    if app:
        app.modo_activo = modo_can

    # 3. Sincronizar solo_dueno si el modo lo exige
    if cfg["solo_dueno"] is True:
        try:
            import pantalla_biometria
            pantalla_biometria.toggle_solo_dueno(app, activar=True)
        except Exception as e:
            print(f"[modos_sistema] Error sincronizando solo_dueno: {e}", flush=True)

    # 4. Ajuste de volumen (en hilo separado para no bloquear)
    vol_obj = cfg["volumen"]
    if vol_obj is not None:
        threading.Thread(target=_ajustar_volumen_pc, args=(vol_obj,), daemon=True).start()

    # 5. Apertura de VS Code en modo programación
    if modo_can == "programacion":
        threading.Thread(target=_abrir_vscode_seguro, args=(app,), daemon=True).start()

    print(f"[modo] activo={modo_can} origen={origen}", flush=True)
    msg = f"Modo {cfg['etiqueta']} activado."
    return True, msg, cfg


def instalar(app):
    """Registra la acción activar_modo en el sistema central de acciones."""
    import acciones

    def _accion_activar_modo(arg=None):
        ok, msg, _ = activar_modo(app, arg or "normal", origen="voz")
        return ok, msg

    acciones.registrar(
        "activar_modo",
        _accion_activar_modo,
        "cambia el modo del sistema: normal, programacion, estudio o noche. Escribe: ACCION: activar_modo | modo",
        con_texto=True,
    )
