"""Enrutador determinista de dos carriles: 'rapido' (gratis) vs 'pro' (avanzado).

La clasificación vive en cerebro_dificultad (fuente única) y el carril Pro en
cerebro_enrutador_pro (cadena verificada con fallback). Este módulo solo
compone ambos y conserva la interfaz pública histórica.
"""
import cerebro_dificultad as cd
from cerebro_enrutador_pro import (
    MAX_TOKENS_PRO,
    PRO_CHAIN,
    completar_pro,
    completar_pro_flujo,
    obtener_cadena_pro,
    obtener_configuracion_pro,
    verificar_pro_disponible,
)

FRASES_EXPLICITAS_PRO = cd.FRASES_EXPLICITAS_PRO
PALABRAS_TECNICAS_PRO = cd.PALABRAS_TECNICAS_PRO
normalizar_texto = cd.normalizar_texto
clasificar_dificultad = cd.clasificar_dificultad


def decidir_carril(texto, modo_activo="normal", pro_disponible=False):
    """Delegado a cerebro_dificultad.decidir_carril (compatibilidad)."""
    return cd.decidir_carril(texto, modo_activo=modo_activo, pro_disponible=pro_disponible)


def _modo_activo(app):
    if app and hasattr(app, "modo_activo"):
        return getattr(app, "modo_activo", "normal") or "normal"
    try:
        import modos_sistema
        return modos_sistema.obtener_modo_activo(app)
    except Exception:
        return "normal"


def ejecutar_con_enrutador(texto, mensajes, tarea="charla", app=None, fallback_fn=None):
    """Enruta a 'pro' o 'rapido' con fallback transparente al carril rápido."""
    modo = _modo_activo(app)
    carril, motivo = decidir_carril(
        texto, modo_activo=modo, pro_disponible=verificar_pro_disponible()
    )
    print(f"[enrutador] carril={carril} motivo={motivo}", flush=True)

    if carril == "pro":
        try:
            return completar_pro(mensajes, tarea=tarea, max_tokens=MAX_TOKENS_PRO)
        except Exception as e:
            print(f"[enrutador] fallback_pro->rapido motivo={e}", flush=True)

    if fallback_fn:
        return fallback_fn(mensajes, tarea=tarea)

    raise RuntimeError("No se pudo completar la solicitud con el enrutador.")
