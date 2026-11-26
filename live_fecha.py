"""Fecha y hora local inyectadas en el prompt de Gemini Live."""
from datetime import datetime

import live_audio

DIAS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def instruccion_con_hora_local(rapido: bool, primer_despertar: bool, nombre_usuario: str) -> str:
    base = live_audio.construir_instruccion_sistema(
        rapido=rapido,
        primer_despertar=primer_despertar,
        nombre_usuario=nombre_usuario,
    )
    ahora = datetime.now()
    fecha = (
        f"{DIAS_ES[ahora.weekday()]} {ahora.day} de {MESES_ES[ahora.month - 1]} "
        f"de {ahora.year}, {ahora.strftime('%H:%M')}"
    )
    return (
        f"{base}\nFecha y hora local actual del usuario: {fecha} "
        "(usa siempre esta fecha y hora local, nunca UTC)."
    )
