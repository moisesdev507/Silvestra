"""Utilidades de estabilidad para el bucle Qt y cola de eventos."""
from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Optional


_bloqueo = threading.RLock()
_ui_minimizada = False
_ui_visible = True
_mostrar_escritorio = False


def actualizar_estado_ui(minimizada: bool = False, visible: bool = True,
                        mostrar_escritorio: bool = False) -> bool:
    global _ui_minimizada, _ui_visible, _mostrar_escritorio
    with _bloqueo:
        _ui_minimizada = bool(minimizada)
        _ui_visible = bool(visible)
        _mostrar_escritorio = bool(mostrar_escritorio)
        return ui_suspender()


def ui_suspender() -> bool:
    with _bloqueo:
        return _ui_minimizada or not _ui_visible or _mostrar_escritorio


def marcar_mostrar_escritorio(activo: bool) -> bool:
    global _mostrar_escritorio
    with _bloqueo:
        _mostrar_escritorio = bool(activo)
        return ui_suspender()


def marcar_modo_escritorio(clase_ventana: str = "") -> bool:
    clase = str(clase_ventana).strip()
    return marcar_mostrar_escritorio(
        clase in ("Progman", "WorkerW", "Shell_TrayWnd")
    )


def puede_actualizar_ui() -> bool:
    return not ui_suspender()


def aplicar_estado_cara(cara, minimizada: bool = False,
                       visible: bool = True,
                       mostrar_escritorio: bool = False) -> bool:
    suspendida = actualizar_estado_ui(
        minimizada=minimizada,
        visible=visible,
        mostrar_escritorio=mostrar_escritorio,
    )
    try:
        if suspendida:
            cara.reloj_dibujo.stop()
            cara.reloj_mover.stop()
            burbuja = getattr(cara, "burbuja", None)
            if burbuja is not None:
                burbuja.hide()
        else:
            if not cara.reloj_dibujo.isActive():
                cara.reloj_dibujo.start(33)
            if not cara.reloj_mover.isActive():
                cara.reloj_mover.start(30)
    except Exception:
        pass
    return suspendida


def crear_accion_segura(menu, titulo: str, confirmacion: str, funcion):
    try:
        from PySide6.QtGui import QAction
        from PySide6.QtCore import QTimer
        accion = menu.addAction(titulo)
        estado = {"confirmada": False}
        timer = QTimer(menu)
        timer.setSingleShot(True)

        def reiniciar():
            estado["confirmada"] = False
            accion.setText(titulo)

        def click():
            if not estado["confirmada"]:
                estado["confirmada"] = True
                accion.setText(confirmacion)
                timer.start(3000)
            else:
                timer.stop()
                reiniciar()
                funcion()

        timer.timeout.connect(reiniciar)
        accion.triggered.connect(click)
        return accion
    except Exception:
        return None


def drenar_cola_acotada(
    cola,
    atender: Callable[[object, object], None],
    max_eventos: int = 8,
    presupuesto_ms: float = 12.0,
) -> tuple[int, bool]:
    procesados = 0
    inicio = time.perf_counter()
    limite = max(1, int(max_eventos))
    presupuesto = max(0.001, float(presupuesto_ms) / 1000.0)
    while procesados < limite:
        if time.perf_counter() - inicio >= presupuesto:
            break
        try:
            tipo, texto = cola.get_nowait()
        except queue.Empty:
            break
        except Exception:
            break
        try:
            atender(tipo, texto)
        except Exception:
            pass
        procesados += 1
    queda = False
    try:
        queda = bool(not cola.empty())
    except Exception:
        queda = False
    return procesados, queda
