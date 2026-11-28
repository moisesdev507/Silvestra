"""Turnos parciales de Gemini Live y contexto conversacional compartido."""
from google.genai import types

import cerebro_unico
import live_audio
import live_fecha
import live_herramientas


def bloque_memoria(max_chars=520):
    """Bloque cognitivo único y estable en cada reconexión de Live."""
    try:
        return "\n" + cerebro_unico.compilar_contexto_unico(
            "", max_chars=max(max_chars, 4000), estable=True)
    except Exception:
        return ""


def construir_config(voz, rapido=False, despertar=False, nombre="", primer_saludo: bool = True):
    """Config Live: una sola fecha y un único bloque cognitivo (ficha, hilo, memoria, subjetividad)."""
    base = live_fecha.instruccion_con_hora_local(rapido, despertar, nombre, primer_saludo=primer_saludo)
    memoria = bloque_memoria()
    instruccion = base + "\n" + memoria
    try:
        import puente_subjetividad
        puente = puente_subjetividad.obtener_puente()
        sub = puente.construir_contexto_identidad()
        if sub:
            instruccion += "\n" + sub
        if primer_saludo:
            saludo_sugerido = puente.construir_saludo_arranque()
            if saludo_sugerido:
                instruccion += (
                    f"\n[SALUDO INICIAL AL CONECTAR]\n"
                    f"Si inicias saludando, di una frase breve (3 a 8 palabras) en este tono: '{saludo_sugerido}'"
                )
    except Exception:
        pass

    realtime_input_config = None
    try:
        realtime_input_config = types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                silence_duration_ms=850,
                prefix_padding_ms=180,
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
            )
        )
    except Exception:
        pass

    config_kwargs = {
        "response_modalities": ["AUDIO"],
        "speech_config": types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voz)
            )
        ),
        "system_instruction": types.Content(parts=[types.Part.from_text(text=instruccion)]),
        "tools": live_herramientas.declarar_declaraciones_herramientas(),
        **live_audio.configuracion_transcripcion(),
    }
    if realtime_input_config is not None:
        config_kwargs["realtime_input_config"] = realtime_input_config

    return types.LiveConnectConfig(**config_kwargs)


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
        if usuario or kaya:
            try:
                import puente_subjetividad
                p = puente_subjetividad.obtener_puente()
                if usuario:
                    p.registrar_turno("usuario", usuario)
                if kaya:
                    p.registrar_turno("kaya", kaya)
            except Exception:
                pass
        return bool(usuario or kaya)


__all__ = ["AcumuladorTurnos", "bloque_memoria", "construir_config"]
