"""Turnos parciales de Gemini Live y contexto conversacional compartido."""
from google.genai import types

import cerebro_unico
import live_audio
import live_fecha
import live_herramientas
import memoria_contexto
import memoria_unificada


def bloque_memoria(max_chars=520):
    """Bloque cognitivo único y estable en cada reconexión de Live."""
    try:
        return "\n" + cerebro_unico.compilar_contexto_unico(
            "", max_chars=max(max_chars, 4000), estable=True)
    except Exception:
        return ""


def bloque_conversacion(max_turnos=12, max_chars=1400):
    """Inyecta el hilo real compartido en el system_instruction de Live."""
    try:
        turnos = memoria_contexto.historial_conversacion_activa(max_turnos, max_chars)
    except Exception:
        turnos = []
    if not turnos:
        return ""
    lineas = [
        f"{'Usuario' if t['role'] == 'user' else 'Kaya'}: {t['content']}"
        for t in turnos
    ]
    return (
        "\n[Conversación reciente en curso] Resuelve 'eso', 'a qué te refieres', "
        "'lo anterior' y 'sígueme contando' con este hilo antes de responder.\n"
        + "\n".join(lineas)
    )


def construir_config(voz, rapido=False, despertar=False, nombre=""):
    """Config Live reconstruida en cada conexión, con el hilo más reciente."""
    base = live_fecha.instruccion_con_hora_local(rapido, despertar, nombre)
    memoria = bloque_memoria()
    instruccion = base + memoria
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voz)
            )
        ),
        system_instruction=types.Content(parts=[types.Part.from_text(text=instruccion)]),
        tools=live_herramientas.declarar_declaraciones_herramientas(),
        **live_audio.configuracion_transcripcion(),
    )


class AcumuladorTurnos:
    """Une fragmentos parciales y guarda el turno completo al cerrarlo."""

    def __init__(self):
        self.usuario = []
        self.kaya = []

    @staticmethod
    def _agregar(destino, texto):
        limpio = " ".join(str(texto or "").split())
        if not limpio:
            return
        if destino:
            anterior = destino[-1]
            if limpio.startswith(anterior):
                destino[-1] = limpio
                return
            if anterior.startswith(limpio):
                return
        destino.append(limpio)

    def agregar_usuario(self, texto):
        self._agregar(self.usuario, texto)

    def agregar_kaya(self, texto):
        self._agregar(self.kaya, texto)

    def vaciar(self):
        """Persiste usuario y Kaya; devuelve True si había algo acumulado."""
        usuario = " ".join(self.usuario).strip()
        kaya = " ".join(self.kaya).strip()
        self.usuario, self.kaya = [], []
        if usuario:
            cerebro_unico.procesar_turno_cognitivo("usuario", usuario, origen="live")
        if kaya:
            cerebro_unico.procesar_turno_cognitivo("kaya", kaya, origen="live")
        return bool(usuario or kaya)


__all__ = ["AcumuladorTurnos", "bloque_memoria", "bloque_conversacion", "construir_config"]
