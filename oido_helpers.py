"""Filtros y barge-in del oído clásico, extraídos para mantener oido.py compacto."""
import re

UMBRAL_CONFIANZA = 0.85


def confianza_resultado(resultado, por_defecto=1.0):
    """Confianza de Deepgram (WS o HTTP); 1.0 si el proveedor no la reporta."""
    try:
        valor = resultado[2] if len(resultado) > 2 else por_defecto
    except Exception:
        return por_defecto
    if valor is None:
        return por_defecto
    try:
        return float(valor)
    except (TypeError, ValueError):
        return por_defecto


def debe_usar_whisper(resultado):
    """Solo respalda con Whisper si falló Deepgram o la confianza es < 0.85."""
    if not resultado:
        return True
    return confianza_resultado(resultado) < UMBRAL_CONFIANZA


def cerrar_ws_al_salir(fn):
    """Cierra la sesión WebSocket aunque la escucha se cancele a mitad de frase."""
    def envuelto(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        finally:
            sesion = getattr(self, "_sesion_ws_actual", None)
            if sesion is not None:
                sesion.cerrar()
                self._sesion_ws_actual = None
    return envuelto


def barge_in_habilitado():
    try:
        import charla_continua
        return charla_continua.barge_in_habilitado()
    except Exception:
        return True


def barge_in(app, datos, comandos_corte, rec_vosk):
    try:
        import charla_continua
        if charla_continua.evaluar_barge_in_seguro(app, datos):
            return True
    except Exception:
        pass
    if rec_vosk is None or not (app and hasattr(app, "voz") and app.voz.ocupada()):
        return False
    try:
        rec_vosk.AcceptWaveform(datos.tobytes())
        m = re.search(r'"partial"\s*:\s*"([^"]+)"', rec_vosk.PartialResult())
        if not m:
            return False
        limpio = re.sub(r"[^a-záéíóúñü\s]", " ", m.group(1).strip().lower())
        palabras = limpio.split()
        if len("".join(palabras)) < 2 or not any(c in palabras for c in comandos_corte):
            return False
        if hasattr(app.voz, "detener"):
            app.voz.detener()
        if hasattr(app, "cola"):
            app.cola.put(("interrupcion", "comando"))
        return True
    except Exception:
        return False


def es_eco_prompt(texto_original, texto, prompt, ultimo_dicho=""):
    import oido_filtro
    return oido_filtro.debe_descartar(texto_original, texto, prompt, ultimo_dicho)


def motivo_descarte_transcripcion(texto, rms, r=None):
    import oido_flujo
    t_low = " ".join(str(texto or "").lower().split())
    if oido_flujo.es_cortesia_corta(texto):
        if oido_flujo.cortesia_descartada(texto, rms, r):
            return f"cortesia_sin_voz_clara(rms={float(rms or 0.0):.1f})"
        return None
        # Las cortesías claras se conservan: son interacciones reales.
    for f in oido_flujo.FALSAS + oido_flujo.CORTESIAS_AMBIGUAS:
        if f in t_low:
            return f"alucinacion_whisper('{f}')"
    return None
