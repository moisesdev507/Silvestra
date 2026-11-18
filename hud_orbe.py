"""Componentes visuales del orbe Jarvis y métricas del sistema para el HUD."""
import math
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

# Intento de psutil con respaldo en ctypes (kernel32)
try:
    import psutil
except ImportError:
    psutil = None

_last_idle = None
_last_kernel = None
_last_user = None


def obtener_metricas():
    """Devuelve (cpu_pct, ram_pct) usando psutil o ctypes nativo de Windows."""
    global _last_idle, _last_kernel, _last_user
    if psutil is not None:
        try:
            return int(psutil.cpu_percent(interval=None)), int(psutil.virtual_memory().percent)
        except Exception:
            pass
    # Respaldo nativo en Windows
    cpu_pct, ram_pct = 0, 0
    try:
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            ram_pct = int(stat.dwMemoryLoad)

        idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
        if ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            i = (idle.dwHighDateTime << 32) | idle.dwLowDateTime
            k = (kernel.dwHighDateTime << 32) | kernel.dwLowDateTime
            u = (user.dwHighDateTime << 32) | user.dwLowDateTime
            if _last_idle is not None:
                usr = u - _last_user
                ker = k - _last_kernel
                idl = i - _last_idle
                sys_tot = ker + usr
                if sys_tot > 0:
                    cpu_pct = max(0, min(100, int((sys_tot - idl) * 100 / sys_tot)))
            _last_idle, _last_kernel, _last_user = i, k, u
    except Exception:
        pass
    return cpu_pct, ram_pct


class OrbeJarvis(QWidget):
    """Orbe animado estilo Jarvis que reacciona al estado de Silvestra."""

    def __init__(self, app, parent=None, tamano=50):
        super().__init__(parent)
        self.app = app
        self.tamano = tamano
        self.setFixedSize(tamano, tamano)
        self.fase = 0
        self.angulo = 0

    def avanzar(self):
        self.fase = (self.fase + 4) % 360
        self.angulo = (self.angulo + 3) % 360
        self.update()

    def estado_actual(self):
        if getattr(self.app, "descansando", False):
            return "reposo"
        if getattr(self.app, "escuchando", False):
            return "escuchando"
        if hasattr(self.app, "cara") and getattr(self.app.cara, "pensando", False):
            return "pensando"
        if hasattr(self.app, "voz") and self.app.voz.ocupada():
            return "hablando"
        return "activo"

    def paintEvent(self, _):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            cx, cy = self.width() / 2, self.height() / 2
            w = self.width()
            est = self.estado_actual()

            if est == "reposo":
                col_base, col_pulso = QColor(51, 65, 85), QColor(100, 116, 139)
            elif est == "escuchando":
                col_base, col_pulso = QColor(245, 158, 11), QColor(254, 240, 138)
            elif est == "pensando":
                col_base, col_pulso = QColor(124, 58, 237), QColor(192, 132, 252)
            elif est == "hablando":
                col_base, col_pulso = QColor(6, 182, 212), QColor(165, 243, 252)
            else:
                col_base, col_pulso = QColor(14, 165, 233), QColor(186, 230, 253)

            # Anillo exterior rotatorio
            p.setPen(QPen(col_base, max(1.5, w * 0.04)))
            p.drawArc(int(w * 0.08), int(w * 0.08), int(w * 0.84), int(w * 0.84), int(self.angulo * 16), int(120 * 16))
            p.drawArc(int(w * 0.08), int(w * 0.08), int(w * 0.84), int(w * 0.84), int((self.angulo + 180) * 16), int(80 * 16))

            # Anillo medio pulsante
            pulso = math.sin(math.radians(self.fase))
            r_int = max(4.0, (w * 0.3) + pulso * (w * 0.06))
            p.setPen(QPen(col_pulso, max(1.0, w * 0.03)))
            p.drawEllipse(int(cx - r_int), int(cy - r_int), int(r_int * 2), int(r_int * 2))

            # Núcleo brillante
            grad = QRadialGradient(cx, cy, w * 0.2)
            grad.setColorAt(0, col_pulso)
            col_t = QColor(col_base)
            col_t.setAlpha(0)
            grad.setColorAt(1, col_t)
            p.setPen(Qt.NoPen)
            p.setBrush(grad)
            r_core = max(4, int(w * 0.16))
            p.drawEllipse(int(cx - r_core), int(cy - r_core), r_core * 2, r_core * 2)
        finally:
            p.end()
