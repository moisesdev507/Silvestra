"""Coreografías de baile, partículas musicales y anillos HUD reactivos para Silvestra."""
import math
import random
import time

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QFont

DURACION_BAILE_SEG = 15.0
ESTILOS_VALIDOS = ("groove", "salsa", "fiesta")

COLORES_NEON = [
    QColor(0, 240, 255),    # Cian neón
    QColor(255, 0, 128),    # Magenta neón
    QColor(255, 220, 0),    # Amarillo neón
    QColor(57, 255, 20),    # Verde neón
    QColor(168, 85, 247),   # Púrpura neón
]

SIMBOLOS_PARTICULAS = ["♪", "♫", "♩", "♬", "✦", "★"]


class ParticulaMusical:
    """Partícula ligera que flota hacia arriba mientras se desvanece."""

    def __init__(self, x, y):
        self.x = x + random.uniform(-35, 35)
        self.y = y + random.uniform(-15, 25)
        self.vx = random.uniform(-0.8, 0.8)
        self.vy = random.uniform(-2.2, -1.2)
        self.simbolo = random.choice(SIMBOLOS_PARTICULAS)
        self.color = random.choice(COLORES_NEON)
        self.tamano = random.randint(13, 20)
        self.vida_max = random.uniform(1.2, 2.0)
        self.nacimiento = time.time()
        self.rotacion = random.uniform(-15, 15)
        self.alfa = 255
        self.fuente = QFont("Arial", self.tamano, QFont.Bold)

    def viva(self, ahora):
        return (ahora - self.nacimiento) < self.vida_max

    def actualizar(self, ahora):
        dt = ahora - self.nacimiento
        progreso = min(1.0, dt / self.vida_max)
        self.x += self.vx + 0.3 * math.sin(dt * 4.0)
        self.y += self.vy
        self.alfa = int(255 * (1.0 - progreso) * (0.8 + 0.2 * math.sin(dt * 8.0)))

    def dibujar(self, p):
        if self.alfa <= 5:
            return
        p.save()
        c = QColor(self.color)
        c.setAlpha(max(0, min(255, self.alfa)))
        p.setPen(c)
        p.setFont(self.fuente)
        p.drawText(QPointF(self.x, self.y), self.simbolo)
        p.restore()


class GestorBaile:
    """Gestiona el estado, ritmo, física de coreografía y partículas de la cara."""

    def __init__(self):
        self.activo = False
        self.estilo = "groove"
        self.baile_hasta = 0.0
        self.t_inicio = 0.0
        self.particulas = []
        self.prox_particula = 0.0
        self.musica_lanzada = False

    def iniciar(self, estilo="aleatorio", segundos=DURACION_BAILE_SEG, app=None, con_musica=True, consulta_usuario=None):
        ahora = time.time()
        est_limpio = str(estilo or "").strip().lower()

        if est_limpio in ("parar", "stop", "detener", "para"):
            self.detener(app=app)
            return False, "Baile detenido."

        if est_limpio not in ESTILOS_VALIDOS:
            est_limpio = random.choice(ESTILOS_VALIDOS)

        self.activo = True
        self.estilo = est_limpio
        self.t_inicio = ahora
        dur = float(segundos or DURACION_BAILE_SEG)
        self.baile_hasta = ahora + dur
        self.particulas.clear()
        self.prox_particula = ahora
        self.musica_lanzada = False

        print(f"[baile] iniciado estilo={self.estilo} musica={con_musica} duracion={dur}s", flush=True)

        if con_musica:
            try:
                import baile_audio
                self.musica_lanzada = baile_audio.reproducir_musica_baile(self.estilo)
            except Exception as e:
                print(f"[baile] musica_error={e}", flush=True)

        return True, f"Bailando estilo {self.estilo}."

    def detener(self, app=None):
        if not self.activo and not self.musica_lanzada:
            return
        self.activo = False
        self.baile_hasta = 0.0
        self.particulas.clear()
        print("[baile] detenido", flush=True)
        if self.musica_lanzada:
            self.musica_lanzada = False
            try:
                import baile_audio
                baile_audio.detener_musica_baile()
            except Exception:
                pass

    def actualizar_fisica(self, ahora, fx, fy, ancho_pantalla, alto_pantalla, tam_cara=208):
        """Calcula el desplazamiento relativo (dx, dy), inclinación y emoción del estilo activo."""
        if not self.activo or ahora >= self.baile_hasta:
            if self.activo:
                self.detener()
            return 0.0, 0.0, 0.0, "neutral"

        t = ahora - self.t_inicio

        # 1. Groove: balanceo armónico vertical suave y pasos cortos
        if self.estilo == "groove":
            dx = 15.0 * math.sin(t * 6.0)
            dy = -12.0 * abs(math.sin(t * 6.0))
            tilt = 6.0 * math.sin(t * 6.0)
            emocion = "alegre"

        # 2. Salsa: marcado lateral vivo y rebote en cadencia cruzada
        elif self.estilo == "salsa":
            dx = 28.0 * math.sin(t * 8.5)
            dy = 8.0 * math.cos(t * 17.0)
            tilt = 14.0 * math.sin(t * 8.5)
            emocion = "calida"

        # 3. Fiesta: saltos enérgicos y desplazamientos alegres
        else:
            dx = 38.0 * math.sin(t * 11.5) + 14.0 * math.sin(t * 3.8)
            dy = -26.0 * abs(math.sin(t * 11.5))
            tilt = 18.0 * math.sin(t * 11.5)
            emocion = "animada"

        # Desplazamiento elástico acotado al lienzo compacto (208 px) sin recortar
        nx = max(-20.0, min(20.0, dx * 0.82))
        ny = max(-18.0, min(18.0, dy * 0.82))

        # Generar partículas musicales
        if ahora >= self.prox_particula and len(self.particulas) < 16:
            self.particulas.append(ParticulaMusical(0, -20))
            self.prox_particula = ahora + (0.12 if self.estilo == "fiesta" else 0.22)

        return nx, ny, tilt, emocion

    def actualizar_particulas(self, ahora):
        self.particulas = [p for p in self.particulas if p.viva(ahora)]
        for p in self.particulas:
            p.actualizar(ahora)

    def dibujar_particulas(self, painter):
        for p in self.particulas:
            p.dibujar(painter)


_GESTOR_GLOBAL = None


def obtener_gestor_baile():
    global _GESTOR_GLOBAL
    if _GESTOR_GLOBAL is None:
        _GESTOR_GLOBAL = GestorBaile()
    return _GESTOR_GLOBAL


def parsear_comando_baile(texto):
    """Extrae el estilo y si pidió bailar con/sin música a partir del texto del usuario."""
    t_norm = (texto or "").strip().lower()

    if any(k in t_norm for k in ("parar", "para", "detener", "deja de bailar", "stop", "quieto")):
        return "parar", False, None

    con_musica = not any(k in t_norm for k in ("sin musica", "sin sonido", "silencio", "mudo"))

    estilo = "aleatorio"
    for e in ESTILOS_VALIDOS:
        if e in t_norm:
            estilo = e
            break

    # Si mencionó una canción específica (ej. "baila despacito", "baila con bachata")
    cancion = None
    for p in ("con la cancion", "la cancion", "con cancion", "con musica de", "al ritmo de", "con"):
        if p in t_norm:
            partes = t_norm.split(p, 1)
            if len(partes) > 1 and len(partes[1].strip()) > 2:
                cancion = partes[1].strip()
                break

    return estilo, con_musica, cancion


def obtener_estilo_anillos(modo_activo, bailando, t):
    """Devuelve los colores neón, pulso y velocidad angular según el modo operativo o baile."""
    if bailando:
        # Neón psicodélico alternante según el ritmo
        idx = int((t * 3.5) % len(COLORES_NEON))
        c1 = COLORES_NEON[idx]
        c2 = COLORES_NEON[(idx + 1) % len(COLORES_NEON)]
        vel = 140.0
        pulso = 0.5 + 0.5 * math.sin(t * 9.0)
        return c1, c2, vel, pulso

    m = (modo_activo or "normal").strip().lower()

    if m == "programacion":
        # Cian neón y azul eléctrico con rotación técnica rápida
        c1 = QColor(0, 240, 255)
        c2 = QColor(37, 99, 235)
        vel = 65.0
        pulso = 0.5 + 0.5 * math.sin(t * 3.5)
    elif m == "estudio":
        # Turquesa zen y ámbar suave muy estable
        c1 = QColor(45, 212, 191)
        c2 = QColor(245, 158, 11)
        vel = 32.0
        pulso = 0.6 + 0.4 * math.sin(t * 1.8)
    elif m == "noche":
        # Azul profundo tenue de bajo brillo
        c1 = QColor(30, 58, 138)
        c2 = QColor(71, 85, 105)
        vel = 18.0
        pulso = 0.4 + 0.2 * math.sin(t * 1.0)
    else:
        # Modo normal: cian clásico y verde esmeralda
        c1 = QColor(79, 209, 197)
        c2 = QColor(16, 185, 129)
        vel = 40.0
        pulso = 0.5 + 0.5 * math.sin(t * 2.2)

    return c1, c2, vel, pulso
