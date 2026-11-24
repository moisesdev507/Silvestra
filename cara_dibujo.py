"""Dibujo de la cara de Silvestra como núcleo J.A.R.V.I.S. reactivo.

La API pública (TAM, CIAN, AMARILLO, GRIS, color_estado, con_alpha, pintar)
permanece intacta; la geometría y los estados viven en ``cara_nucleo``.
"""
import time

from PySide6.QtGui import QPainter

import cara_emociones
import cara_nucleo

TAM = 208               # tamaño compacto de la ventana de la cara (-17%)
ESC = TAM / 280.0       # escala proporcional del dibujo
CIAN = cara_nucleo.CELESTE
AMARILLO = cara_nucleo.AMBAR
ROSA = cara_nucleo.ROSA
GRIS = cara_nucleo.GRIS

PERFILES_EMOCION = cara_emociones.RASGOS_FACIALES


def color_estado(viva, escuchando, hablando, feliz=False, base=None, silenciada=False):
    """Celeste en reposo; ámbar al escuchar/hablar; gris si apagada o silenciada."""
    return cara_nucleo.color_estado(viva, escuchando, hablando,
                                    feliz, base, silenciada)


def con_alpha(color, a):
    return cara_nucleo.alpha(color, a)


def _asegurar_atributos(cara):
    """Garantiza los pocos estados que el núcleo necesita para pintar."""
    if not getattr(cara, "_nucleo_inicializado", False):
        cara._nucleo_inicializado = True
        cara._nivel_suave = 0.0
        cara._color_r = float(cara_nucleo.CELESTE.red())
        cara._color_g = float(cara_nucleo.CELESTE.green())
        cara._color_b = float(cara_nucleo.CELESTE.blue())
        cara._energia_suave = 0.0
        cara._radio_suave = 52.0
        cara._sonrisa_suave = 0.0
    if not hasattr(cara, "t0"):
        cara.t0 = time.time()
    valores = {
        "feliz_hasta": 0.0, "baile_hasta": 0.0, "pensando": False,
        "pensando_hasta": 0.0, "emocion_objetivo": "neutral", "mx": 0.0,
    }
    for clave, valor in valores.items():
        if not hasattr(cara, clave):
            setattr(cara, clave, valor)


def pintar(cara):
    """Pinta el orbe híbrido (Núcleo Vivo + Halo Técnico) sin bloquear el hilo de Qt."""
    _asegurar_atributos(cara)
    ahora = time.time()
    p = QPainter(cara)
    try:
        import cara_orbe_hibrido
        cara_orbe_hibrido.dibujar_orbe_hibrido(p, cara, ahora - cara.t0,
                                               cara.width() or TAM)
    except Exception:
        # Fallback defensivo a cara_nucleo si ocurriera cualquier error
        feliz = ahora < cara.feliz_hasta or ahora < cara.baile_hasta
        color = color_estado(
            getattr(cara, "viva", True),
            getattr(cara, "escuchando", False),
            getattr(cara, "hablando", False),
            feliz,
            silenciada=cara_nucleo.esta_silenciada(cara),
        )
        cara_nucleo.dibujar(p, cara, color, ahora - cara.t0,
                            cara.width() or TAM)
    finally:
        p.end()
