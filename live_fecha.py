"""Fecha y hora local inyectadas en el prompt de Gemini Live."""
from datetime import datetime

import live_audio

DIAS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def instruccion_con_hora_local(rapido: bool, primer_despertar: bool, nombre_usuario: str) -> str:
    """Identidad + guía sin fecha ni memoria: añade una sola fecha local.

    La memoria/ficha/hilo se inyecta después desde la única compilación de
    `cerebro_unico`, así que esta base no debe incluir `contexto_memoria()`.
    """
    base = live_audio.construir_instruccion_sistema(
        rapido=rapido,
        primer_despertar=primer_despertar,
        nombre_usuario=nombre_usuario,
        incluir_fecha=False,
        incluir_memoria=False,
        max_chars=3000,
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
