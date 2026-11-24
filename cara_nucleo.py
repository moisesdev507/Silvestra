"""Núcleo holográfico J.A.R.V.I.S. dinámico y reactivo.

API pública intacta: constantes de paleta, ``color_estado``, ``esta_silenciada``,
``modo``, ``nivel``, ``registrar_cuadro``, ``alpha``, ``color_suavizado`` y
``dibujar``. Toda la animación vive aquí y sus estados internos se crean solos.
"""
import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient

CELESTE = QColor(34, 211, 238)
CELESTE_CLARO = QColor(56, 189, 248)
AMBAR = QColor(245, 158, 11)
AMBAR_CLARO = QColor(251, 191, 36)
GRIS = QColor(100, 116, 139)
ROSA = QColor(244, 114, 182)


def registrar_cuadro(cara, dt):
    """Telemetría ligera de FPS fuera del widget (mantiene cara_qt delgada)."""
    cara._tiempo_dibujo_acum += dt
    cara._fps_cuadros += 1
    ahora = time.time()
    dt_fps = ahora - cara._fps_t0
    if dt_fps >= 5.0:
        fps = cara._fps_cuadros / dt_fps
        cpu = (cara._tiempo_dibujo_acum / dt_fps) * 100.0
        print(f"[cara] fps={fps:.1f}, cpu_estimada={cpu:.1f}%", flush=True)
        cara._fps_cuadros = 0
        cara._fps_t0 = ahora
        cara._tiempo_dibujo_acum = 0.0


def alpha(color, a):
    c = QColor(color)
    c.setAlpha(max(0, min(255, int(a))))
    return c


def color_estado(viva, escuchando, hablando, feliz=False, base=None, silenciada=False):
    if silenciada or not viva:
        return GRIS
    if escuchando or hablando:
        return AMBAR
    if feliz:
        return ROSA
    return base if base is not None else CELESTE


def esta_silenciada(cara):
    valor = getattr(cara, "voz_silenciada", None)
    if valor is None:
        app = getattr(cara, "silvestra_app", None) or getattr(cara, "_ref_app", None)
        valor = getattr(app, "voz_silenciada", False)
    return bool(valor)


def modo(cara):
    if esta_silenciada(cara):
        return "silenciada"
    if getattr(cara, "hablando", False):
        return "hablando"
    if getattr(cara, "escuchando", False) or getattr(cara, "pensando", False):
        return "escuchando"
    return "reposo"


def nivel(cara):
    if esta_silenciada(cara):
        objetivo = 0.0
    else:
        try:
            objetivo = float(getattr(cara, "nivel_volumen", 0.0) or 0.0)
        except Exception:
            objetivo = 0.0
        objetivo = max(0.0, min(1.0, objetivo))
    suave = float(getattr(cara, "_nivel_suave", 0.0))
    suave += (objetivo - suave) * 0.25
    cara._nivel_suave = suave
    return suave


def _lerp(cara, clave, objetivo, factor):
    actual = float(getattr(cara, clave, objetivo))
    actual += (float(objetivo) - actual) * factor
    setattr(cara, clave, actual)
    return actual


def color_suavizado(cara, objetivo, factor=0.12):
    """Interpola RGB entre estados; el cambio nunca es brusco de un frame."""
    r = _lerp(cara, "_color_r", objetivo.red(), factor)
    g = _lerp(cara, "_color_g", objetivo.green(), factor)
    b = _lerp(cara, "_color_b", objetivo.blue(), factor)
    return QColor(round(r), round(g), round(b))


def _inicializar(cara):
    """Estados de animación bajo demanda; no altera la API de la cara."""
    valores = {
        "_ultimo_t": None, "_vel_ang": 0.35, "_fase_anillos": 0.0,
        "_nivel_previo": 0.0, "_ultima_onda": 0.0, "_ondas": [],
    }
    for clave, valor in valores.items():
        if not hasattr(cara, clave):
            setattr(cara, clave, valor)


def _respiracion(t):
    """Doble seno desfasado: inspira y espira con ritmo orgánico."""
    return 0.5 + 0.25 * math.sin(t * 0.75) + 0.25 * math.sin(t * 1.31 + 0.7)


def _dinamica(cara, estado, energia, nivel_actual, t):
    """Inercia angular de los anillos y disparo de ondas por picos de voz."""
    anterior = getattr(cara, "_ultimo_t", None)
    dt = 0.016 if anterior is None else max(0.001, min(0.1, t - anterior))
    cara._ultimo_t = t
    if estado == "silenciada":
        objetivo = 0.0
    elif estado == "reposo":
        objetivo = 0.35
    else:
        objetivo = 1.0 + 2.6 * energia
    vel = _lerp(cara, "_vel_ang", objetivo, 0.08)
    fase = float(getattr(cara, "_fase_anillos", 0.0)) + vel * dt * 22.0
    cara._fase_anillos = fase % 360.0

    ondas = getattr(cara, "_ondas", [])
    if estado == "hablando" and energia > 0.18:
        pico = nivel_actual - float(getattr(cara, "_nivel_previo", 0.0))
        armonico = 0.5 + 0.5 * math.sin(t * 9.0)
        if ((pico > 0.05 and armonico > 0.5)
                or (t - float(getattr(cara, "_ultima_onda", 0.0))) > 0.42):
            ondas.append({"t0": t, "fuerza": 0.55 + 0.45 * min(1.0, nivel_actual)})
            cara._ultima_onda = t
            if len(ondas) > 5:
                ondas.pop(0)
    cara._nivel_previo = nivel_actual
    cara._ondas = [o for o in ondas if t - o["t0"] < 0.85]
    return vel, cara._fase_anillos


def _halo(p, color, energia, silenciada, t, respiracion):
    radio = 130 + 6 * energia + (5 * respiracion if not silenciada else 0.0)
    g = QRadialGradient(QPointF(0, 0), radio)
    g.setColorAt(0.45, alpha(color, 30 if silenciada else int(66 + 38 * energia)))
    g.setColorAt(0.82, alpha(color, 14))
    g.setColorAt(1.0, alpha(color, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(0, 0), radio, radio)
    if silenciada:
        return
    for k in range(12):
        ang = t * (0.45 + 0.12 * (k % 3)) + k * 2.39996
        r = 112 + (k % 5) * 6 + 6 * energia
        punto = QPointF(r * math.cos(ang), r * math.sin(ang))
        p.setBrush(alpha(CELESTE_CLARO if energia < 0.3 else AMBAR_CLARO,
                         40 + int(65 * energia)))
        p.drawEllipse(punto, 1.2, 1.2)


def _anillos(p, color, estado, energia, fase, vel):
    silenciada = estado == "silenciada"
    anillos = ((116, 2.8, 1.0, 112), (101, 1.9, -0.78, 86), (132, 1.5, 0.55, 62))
    if silenciada:
        anillos = ((116, 2.0, 0.0, 340), (101, 1.4, 0.0, 340))
    for indice, (radio, grosor, factor, largo) in enumerate(anillos):
        pluma = QPen(alpha(color, (70 if silenciada else 135) + int(70 * energia)),
                     grosor)
        pluma.setCapStyle(Qt.RoundCap)
        p.setPen(pluma)
        p.setBrush(Qt.NoBrush)
        rect = QRectF(-radio, -radio, radio * 2, radio * 2)
        ini = (fase * factor + indice * 47) % 360
        p.drawArc(rect, int(ini * 16), int(largo * 16))
        if silenciada:
            continue
        p.drawArc(rect, int((ini + 140) * 16), int(largo * 16))
        p.drawArc(rect, int((ini + 265) * 16), int(largo * 16))
        # Puntos de telemetría recorriendo el anillo.
        for m in range(12):
            a = math.radians(m * 30 + ini * 0.7)
            x, y = math.cos(a), math.sin(a)
            pluma.setWidthF(0.9)
            p.setPen(pluma)
            p.drawLine(QPointF(radio * x, radio * y),
                       QPointF((radio + 4 + 2 * vel) * x, (radio + 4 + 2 * vel) * y))
            if m % 4 == 0:
                p.setBrush(alpha(AMBAR_CLARO if energia > 0.3 else CELESTE_CLARO,
                                 90 + int(60 * energia)))
                p.drawEllipse(QPointF(radio * x, radio * y), 1.6, 1.6)


def _espectro(p, color, estado, energia, t, fase):
    if estado == "silenciada":
        return
    tono = AMBAR_CLARO if estado == "hablando" else CELESTE_CLARO
    base = 78
    for i in range(48):
        if i % 2 and energia < 0.2:
            continue
        ang = i * math.tau / 48.0 + math.radians(fase) * 0.5
        var = abs(math.sin(t * (4.2 + i * 0.06) + i * 0.71))
        armonico = 0.5 + 0.5 * math.sin(t * 8.0 + i * 0.33)
        largo = 2 + 17 * energia * (0.6 * var + 0.4 * armonico)
        c, s = math.cos(ang), math.sin(ang)
        p.setPen(QPen(alpha(tono, 32 + int(100 * energia * var)), 1.15))
        p.drawLine(QPointF(base * c, base * s),
                   QPointF((base + largo) * c, (base + largo) * s))
    for k in range(3):
        radio = 88 + k * 14 + 6 * energia * math.sin(t * 5 + k)
        p.setPen(QPen(alpha(color, 60 + int(45 * energia) - k * 12), 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(-radio, -radio, radio * 2, radio * 2))


def _ondas_choque(p, ondas, t):
    """Ondas concéntricas expansivas disparadas por los picos de voz."""
    for onda in ondas:
        edad = t - onda["t0"]
        if not 0.0 <= edad < 0.85:
            continue
        avance = edad / 0.85
        radio = 58 + 110 * avance
        a = int((1.0 - avance) ** 1.6 * 165 * onda["fuerza"])
        p.setPen(QPen(alpha(AMBAR_CLARO, a), 1.7))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(-radio, -radio, radio * 2, radio * 2))


def _radar(p, energia, fase, t):
    """Barrido orbital ámbar con estela luminosa y eco reactivo al micrófono."""
    ang = math.radians((fase * 1.6) % 360)
    rect = QRectF(-112, -112, 224, 224)
    for k in range(8):
        ini = math.degrees(ang) - 34 - k * 4
        a = int(120 * (1.0 - k / 8.0) * (0.55 + 0.45 * energia))
        p.setPen(QPen(alpha(AMBAR_CLARO, a), 2.4 - k * 0.2))
        p.setBrush(Qt.NoBrush)
        p.drawArc(rect, int(ini * 16), int(13 * 16))
    p.setPen(QPen(alpha(AMBAR_CLARO, 150 + int(80 * energia)), 1.5))
    p.drawLine(QPointF(0, 0), QPointF(112 * math.cos(ang), 112 * math.sin(ang)))
    pulso = 18 + 13 * energia * (0.5 + 0.5 * math.sin(t * 10.0))
    p.setPen(QPen(alpha(AMBAR_CLARO, 90 + int(90 * energia)), 1.2))
    p.drawEllipse(QPointF(0, 0), pulso, pulso)


def _particulas(p, energia, t):
    """Micro-partículas orbitales flotando en reposo y en actividad."""
    for i in range(18):
        ang = t * (0.22 + 0.03 * (i % 5)) + i * 2.39996
        radio = 122 + (i % 6) * 4 + 3 * math.sin(t * 0.9 + i)
        punto = QPointF(radio * math.cos(ang), radio * math.sin(ang))
        brillo = 40 + int(55 * (0.5 + 0.5 * math.sin(t * 1.7 + i * 0.8)))
        p.setPen(Qt.NoPen)
        p.setBrush(alpha(CELESTE_CLARO if energia < 0.3 else AMBAR_CLARO, brillo))
        p.drawEllipse(punto, 0.9 + 0.5 * (i % 3), 0.9 + 0.5 * (i % 3))


def _iris(p, color, sonrisa, energia, estado, t):
    """Arcos del iris: se abren y vibran al hablar, enfocados al escuchar."""
    tono = AMBAR_CLARO if estado in ("escuchando", "hablando") else CELESTE_CLARO
    inicio, arco = (200, 140) if sonrisa >= 0 else (20, 140)
    apertura = 1.0 + (1.2 * energia if estado == "hablando" else 0.0)
    pluma = QPen(alpha(tono, 115 + int(75 * energia)), 2.0)
    pluma.setCapStyle(Qt.RoundCap)
    p.setPen(pluma)
    p.setBrush(Qt.NoBrush)
    for lado in (-1, 1):
        vibra = (2.4 * energia * math.sin(t * 19 + lado) if estado == "hablando"
                 else 1.5 * energia * math.sin(t * 13 + lado))
        y = -1 + 1.5 * sonrisa + vibra
        alto = (14 + 4 * max(0.0, sonrisa)) * apertura
        rect = QRectF(lado * 12 - 13, y - alto / 2.0, 26, alto)
        p.drawArc(rect, int(inicio * 16), int(arco * 16))


def dibujar(p, cara, color, t, tam):
    """Dibuja el núcleo completo; ``t`` es tiempo monótono en segundos."""
    _inicializar(cara)
    estado = modo(cara)
    silenciada = estado == "silenciada"
    nivel_actual = nivel(cara)
    objetivo = 0.0 if silenciada else (
        0.25 + 0.75 * nivel_actual if estado in ("escuchando", "hablando") else 0.12)
    energia = _lerp(cara, "_energia_suave", objetivo, 0.10)
    color_suave = color_suavizado(cara, color)
    vel, fase = _dinamica(cara, estado, energia, nivel_actual, t)
    respiracion = _respiracion(t) if not silenciada else 0.0
    pulso = 0.0 if silenciada else (
        respiracion if estado == "reposo" else 0.35 + 0.65 * energia)
    radio = _lerp(cara, "_radio_suave",
                  52 + ((2.0 * respiracion) if estado == "reposo" else 6.0 * energia)
                  + (1.5 * energia if estado == "hablando" else 0.0), 0.12)
    ahora = time.time()
    feliz = ahora < getattr(cara, "feliz_hasta", 0.0) or ahora < getattr(cara, "baile_hasta", 0.0)
    objetivo_sonrisa = 0.0 if silenciada else (
        0.8 if feliz or estado == "reposo" else
        0.15 if estado == "escuchando" else -0.2)
    sonrisa = _lerp(cara, "_sonrisa_suave", objetivo_sonrisa, 0.10)

    esc = tam / 280.0
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(tam / 2.0, tam / 2.0)
    p.scale(esc, esc)

    _halo(p, color_suave, energia, silenciada, t, respiracion)
    _anillos(p, color_suave, estado, energia, fase, vel)
    if not silenciada:
        _particulas(p, energia, t)
    if estado == "escuchando":
        _radar(p, energia, fase, t)
    _espectro(p, color_suave, estado, energia, t, fase)
    if estado == "hablando":
        _ondas_choque(p, getattr(cara, "_ondas", []), t)

    orbe = QRadialGradient(QPointF(-radio * 0.18, -radio * 0.2), radio)
    orbe.setColorAt(0.0, alpha(CELESTE_CLARO if estado == "reposo" else color_suave, 255))
    orbe.setColorAt(0.45, alpha(color_suave, 225))
    orbe.setColorAt(1.0, alpha(color_suave, 55))
    p.setPen(QPen(alpha(color_suave, 80 if silenciada else 170), 1.8))
    p.setBrush(QBrush(orbe))
    p.drawEllipse(QPointF(0, 0), radio, radio)
    _iris(p, color_suave, sonrisa, energia, estado, t)

    p.setPen(Qt.NoPen)
    p.setBrush(alpha(QColor(255, 255, 255), 55 if silenciada else 150 + int(60 * pulso)))
    p.drawEllipse(QPointF(0, 0), 4 + 2 * pulso, 4 + 2 * pulso)
    p.restore()
