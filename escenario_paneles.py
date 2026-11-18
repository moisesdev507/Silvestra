"""Paneles de alto contraste y tipografía grande legibles desde atrás de un salón."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen

from escenario_estilo import (
    COLOR_CIAN_BRILLO, COLOR_CIAN_MEDIO, COLOR_TEXTO_BLANCO,
    COLOR_TEXTO_ATENUADO, COLOR_AMBAR_ACENTO, dibujar_panel_marco
)


def _dibujar_encabezado_animado(p: QPainter, rect: QRectF, titulo: str, subtitulo: str, anim_fase: float):
    x, y, w = rect.x(), rect.y(), rect.width()
    beam_x = x + (w * anim_fase)
    grad_luz = QLinearGradient(beam_x - 120, y + 38, beam_x + 120, y + 38)
    grad_luz.setColorAt(0.0, QColor(6, 182, 212, 0))
    grad_luz.setColorAt(0.5, COLOR_CIAN_BRILLO)
    grad_luz.setColorAt(1.0, QColor(6, 182, 212, 0))
    p.setPen(QPen(grad_luz, 2.5))
    p.drawLine(QPointF(x + 20, y + 42), QPointF(x + w - 20, y + 42))

    p.setFont(QFont("Segoe UI", 15, QFont.Bold))
    p.setPen(COLOR_CIAN_BRILLO)
    p.drawText(QRectF(x + 24, y + 10, w - 48, 28), Qt.AlignLeft, titulo)

    p.setFont(QFont("Segoe UI", 10))
    p.setPen(COLOR_TEXTO_ATENUADO)
    p.drawText(QRectF(x + 24, y + 46, w - 48, 20), Qt.AlignLeft, subtitulo)


def dibujar_oido(p: QPainter, rect: QRectF, muestras, anim_fase):
    dibujar_panel_marco(p, rect)
    _dibujar_encabezado_animado(p, rect, "OÍDO // RECONOCIMIENTO WHISPER EN VIVO", "Captura de micrófono y detección de energía", anim_fase)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    mid_y = y + h * 0.62
    p.setPen(QPen(COLOR_CIAN_BRILLO, 3.0))
    if len(muestras) > 1:
        dx = (w - 70) / float(len(muestras) - 1)
        puntos = [QPointF(x + 35 + i * dx, mid_y - (min(h * 0.25, amp * 0.12) if i % 2 == 0 else -min(h * 0.25, amp * 0.12))) for i, amp in enumerate(muestras)]
        for i in range(len(puntos) - 1):
            p.drawLine(puntos[i], puntos[i + 1])
    p.setFont(QFont("Segoe UI", 12, QFont.Bold))
    p.setPen(COLOR_TEXTO_BLANCO)
    p.drawText(QRectF(x + 30, y + h - 50, w - 60, 24), Qt.AlignCenter, "ESTADO: MICRÓFONO CONECTADO • VOZ ACTIVA")


def dibujar_cerebro(p: QPainter, rect: QRectF, prov, mod, pt, tot, anim_fase):
    dibujar_panel_marco(p, rect)
    _dibujar_encabezado_animado(p, rect, "CEREBRO // MODELO LLM Y LATENCIA EN VIVO", "Conmutación en milisegundos ante fallos", anim_fase)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    tarjetas = [("PROVEEDOR ACTIVO", prov, COLOR_CIAN_BRILLO), ("MODELO NEURONAL", mod.split("/")[-1], QColor("#c084fc")), ("TIEMPO RESPUESTA", str(tot), COLOR_AMBAR_ACENTO)]
    tw = (w - 60) / 3.0
    for i, (tit, val, col) in enumerate(tarjetas):
        tx, ty, th = x + 24 + i * (tw + 6), y + 78, h - 142
        p.setPen(QPen(QColor(51, 65, 85), 1.5))
        p.setBrush(QColor(15, 23, 42, 220))
        p.drawRoundedRect(QRectF(tx, ty, tw, th), 12, 12)
        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        p.setPen(COLOR_TEXTO_ATENUADO)
        p.drawText(QRectF(tx + 8, ty + 12, tw - 16, 22), Qt.AlignCenter, tit)
        p.setFont(QFont("Segoe UI", 14, QFont.Bold))
        p.setPen(col)
        p.drawText(QRectF(tx + 6, ty + 38, tw - 12, 34), Qt.AlignCenter, str(val))
    p.setFont(QFont("Segoe UI", 11))
    p.setPen(COLOR_TEXTO_BLANCO)
    p.drawText(QRectF(x + 24, y + h - 46, w - 48, 22), Qt.AlignCenter, "Cadena: 1. Groq (Principal) ➔ 2. Google Gemini ➔ 3. OpenRouter")


def dibujar_vision(p: QPainter, rect: QRectF, pixmap, anim_fase):
    dibujar_panel_marco(p, rect)
    _dibujar_encabezado_animado(p, rect, "VISIÓN // RECONOCIMIENTO Y GESTOS MULTIMODAL", "Cámara y pantalla procesadas en RAM", anim_fase)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    vw, vh = int(w * 0.38), int(h * 0.52)
    vx, vy = x + 28, y + 80
    p.setPen(QPen(COLOR_CIAN_MEDIO, 1.5))
    p.setBrush(QColor(10, 16, 28))
    p.drawRect(vx, vy, vw, vh)
    if pixmap and not pixmap.isNull():
        p.drawPixmap(vx, vy, vw, vh, pixmap)
    else:
        p.setFont(QFont("Segoe UI", 11))
        p.setPen(COLOR_TEXTO_ATENUADO)
        p.drawText(QRectF(vx, vy, vw, vh), Qt.AlignCenter, "Captura en memoria...")
    tx = vx + vw + 24
    p.setFont(QFont("Segoe UI", 12, QFont.Bold))
    p.setPen(COLOR_TEXTO_BLANCO)
    p.drawText(QRectF(tx, vy + 4, w - vw - 70, 26), Qt.AlignLeft, "• Visión Multimodal con Groq Vision")
    p.drawText(QRectF(tx, vy + 38, w - vw - 70, 26), Qt.AlignLeft, "• Detección Facial del Dueño (YuNet)")
    p.drawText(QRectF(tx, vy + 72, w - vw - 70, 26), Qt.AlignLeft, "• Gestos de Mano (MediaPipe Hands)")
    p.setFont(QFont("Segoe UI", 10))
    p.setPen(COLOR_CIAN_BRILLO)
    p.drawText(QRectF(tx, vy + 108, w - vw - 70, 24), Qt.AlignLeft, "Privacidad: Contraseñas y tokens excluidos")


def dibujar_casa(p: QPainter, rect: QRectF, luz, vent, puerta, anim_fase):
    dibujar_panel_marco(p, rect)
    _dibujar_encabezado_animado(p, rect, "DOMÓTICA // CONTROL DE CASA INTELIGENTE", "Comandos por voz y gestos de mano", anim_fase)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    dispositivos = [("Luz Sala", luz, "💡", COLOR_AMBAR_ACENTO), ("Ventilador", vent, "🌀", COLOR_CIAN_BRILLO), ("Puerta", puerta, "🚪", QColor("#4fd1c5"))]
    tw = (w - 60) / 3.0
    for i, (nom, activo, icono, col) in enumerate(dispositivos):
        dx, dy, dh = x + 24 + i * (tw + 6), y + 80, h - 140
        p.setPen(QPen(col if activo else QColor(51, 65, 85), 2.0 if activo else 1.0))
        p.setBrush(QColor(15, 23, 42, 235))
        p.drawRoundedRect(QRectF(dx, dy, tw, dh), 12, 12)
        p.setFont(QFont("Segoe UI Emoji", 24))
        p.drawText(int(dx + 16), int(dy + 14), 46, 46, Qt.AlignCenter, icono)
        p.setFont(QFont("Segoe UI", 13, QFont.Bold))
        p.setPen(COLOR_TEXTO_BLANCO)
        p.drawText(QRectF(dx + 70, dy + 14, tw - 80, 26), Qt.AlignLeft, nom)
        p.setFont(QFont("Segoe UI", 12, QFont.Bold))
        p.setPen(col if activo else COLOR_TEXTO_ATENUADO)
        st = ("ABIERTA" if activo else "CERRADA") if "Puerta" in nom else ("ENCENDIDO" if activo else "APAGADO")
        p.drawText(QRectF(dx + 70, dy + 40, tw - 80, 24), Qt.AlignLeft, st)
    p.setFont(QFont("Segoe UI", 11))
    p.setPen(COLOR_TEXTO_BLANCO)
    p.drawText(QRectF(x + 24, y + h - 46, w - 48, 22), Qt.AlignCenter, "Control por voz: 'enciende la luz', 'abre la puerta' o por gestos")


def dibujar_memoria(p: QPainter, rect: QRectF, hechos, ideas_txt, hilos_txt, anim_fase):
    dibujar_panel_marco(p, rect)
    _dibujar_encabezado_animado(p, rect, "MEMORIA // APRENDIZAJE Y DATOS DURADEROS", "Recuerdos persistentes del usuario y temas pendientes", anim_fase)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    hechos_txt = " • ".join(hechos) if hechos else "Esperando interacciones duraderas..."
    p.setFont(QFont("Segoe UI", 12, QFont.Bold))
    p.setPen(COLOR_TEXTO_BLANCO)
    p.drawText(QRectF(x + 28, y + 80, w - 56, 26), Qt.AlignLeft, f"🧠 Aprendido: {hechos_txt[:75]}")
    p.drawText(QRectF(x + 28, y + 116, w - 56, 26), Qt.AlignLeft, f"💡 Ideas anotadas: {ideas_txt[:75]}")
    p.drawText(QRectF(x + 28, y + 152, w - 56, 26), Qt.AlignLeft, f"🧵 Hilos pendientes: {hilos_txt[:75]}")
    p.setFont(QFont("Segoe UI", 10))
    p.setPen(COLOR_CIAN_BRILLO)
    p.drawText(QRectF(x + 28, y + h - 44, w - 56, 22), Qt.AlignCenter, "Proveedores: Groq (principal) • Google Gemini (respaldo) • OpenRouter (libre)")


def dibujar_estudio(p: QPainter, rect: QRectF, anim_fase):
    dibujar_panel_marco(p, rect)
    _dibujar_encabezado_animado(p, rect, "MODO ESTUDIO // ASISTENCIA UNIVERSITARIA", "Herramientas de productividad académica integradas", anim_fase)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    p.setFont(QFont("Segoe UI", 12, QFont.Bold))
    p.setPen(COLOR_TEXTO_BLANCO)
    p.drawText(QRectF(x + 28, y + 82, w - 56, 26), Qt.AlignLeft, "• Temporizador Pomodoro con pausas guiadas por voz")
    p.drawText(QRectF(x + 28, y + 118, w - 56, 26), Qt.AlignLeft, "• Banco de notas y apuntes de voz persistentes")
    p.drawText(QRectF(x + 28, y + 154, w - 56, 26), Qt.AlignLeft, "• Examen oral interactivo de programación")
    p.setFont(QFont("Segoe UI", 11))
    p.setPen(COLOR_CIAN_BRILLO)
    p.drawText(QRectF(x + 28, y + h - 44, w - 56, 22), Qt.AlignCenter, "Comandos: 'estudiar 25 minutos' • 'hazme un examen'")


def dibujar_cierre(p: QPainter, rect: QRectF, anim_fase):
    dibujar_panel_marco(p, rect, brillo_intenso=True)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    p.setFont(QFont("Segoe UI", 18, QFont.Bold))
    p.setPen(COLOR_CIAN_BRILLO)
    p.drawText(QRectF(x + 20, y + 40, w - 40, 32), Qt.AlignCenter, "DEMOSTRACIÓN COMPLETADA")
    p.setFont(QFont("Segoe UI", 13, QFont.Bold))
    p.setPen(COLOR_TEXTO_BLANCO)
    p.drawText(QRectF(x + 20, y + 90, w - 40, 26), Qt.AlignCenter, "Silvestra está lista para responder preguntas del público")
    p.setFont(QFont("Segoe UI", 11))
    p.setPen(COLOR_TEXTO_ATENUADO)
    p.drawText(QRectF(x + 20, y + 130, w - 40, 24), Qt.AlignCenter, "Habla con naturalidad o presiona [Esc] para volver al escritorio")


def dibujar_intro(p: QPainter, rect: QRectF, creador: str, anim_fase):
    dibujar_panel_marco(p, rect)
    _dibujar_encabezado_animado(p, rect, "SILVESTRA // PROTOTIPO DE ASISTENTE IA", f"Proyecto universitario creado por {creador or 'Moisés'} en Panamá", anim_fase)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    p.setFont(QFont("Segoe UI", 12, QFont.Bold))
    p.setPen(COLOR_TEXTO_BLANCO)
    p.drawText(QRectF(x + 28, y + 82, w - 56, 26), Qt.AlignLeft, "• Meta a futuro: vivir en un anillo inteligente para domótica")
    p.drawText(QRectF(x + 28, y + 118, w - 56, 26), Qt.AlignLeft, "• Reconocimiento de voz local y neuronal (Whisper + Edge-TTS)")
    p.drawText(QRectF(x + 28, y + 154, w - 56, 26), Qt.AlignLeft, "• Visión artificial para reconocer al dueño y gestos de la mano")
    p.setFont(QFont("Segoe UI", 11))
    p.setPen(COLOR_CIAN_BRILLO)
    p.drawText(QRectF(x + 28, y + h - 44, w - 56, 22), Qt.AlignCenter, "Hoy funcionando en vivo ante ustedes • Totalmente en Python")
