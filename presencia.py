"""Módulo de presencia de Silvestra: coordina la presencia física con la pantalla remota.

Usa la cámara existente para detectar ausencia (60 s sin personas) y retorno del dueño.
Cuando el dueño está ausente y la pantalla remota está activa, la cara de la laptop
pasa a modo discreto y la tablet muestra la cara grande y activa. Al regresar,
vuelve a la laptop con una transición suave y un saludo opcional con cooldown de 10 min.
"""
import random
import threading
import time

import acciones
import estado

TIEMPO_AUSENCIA_SEGUNDOS = 60.0
INTERVALO_SALUDO_SEGUNDOS = 600.0  # 10 minutos de cooldown


def log(mensaje):
    """Imprime mensajes con el prefijo estandarizado [presencia]."""
    print(f"[presencia] {mensaje}", flush=True)


class GestorPresencia:
    """Gestiona la detección de presencia y coordina la cara entre laptop y tablet."""

    def __init__(self, app):
        self.app = app
        self._bloqueo = threading.Lock()
        self._detener = threading.Event()
        self.discreto_activo = False
        self.ausente = False
        self.tiempo_inicio_ausencia = 0.0
        self.ult_persona = time.time()
        self.ult_saludo = 0.0

        datos = estado.cargar()
        self.activa = bool(datos.get("presencia_activa", False))

        self._hilo = threading.Thread(target=self._bucle, daemon=True, name="PresenciaBucle")
        self._hilo.start()

    def _es_remota_activa(self):
        """Indica si el servidor de pantalla remota para tablet está en ejecución."""
        remota = getattr(self.app, "pantalla_remota", None)
        if not remota:
            return False
        return bool(getattr(remota, "activa", False) or getattr(remota, "_servidor", None) is not None)

    def _bucle(self):
        """Hilo secundario daemon que verifica periódicamente el estado de presencia."""
        while not self._detener.is_set():
            try:
                self._revisar()
            except Exception as e:
                log(f"Error en revisión de presencia: {e}")
            time.sleep(1.0)

    def _revisar(self):
        """Chequea si la cámara está activa y actualiza las transiciones ausente/presente."""
        if not self.activa:
            return

        cam = getattr(self.app, "camara", None)
        if not cam or not getattr(cam, "activa", False):
            # Cámara apagada: no hacer nada y no dar error
            return

        ahora = time.time()
        ult_rostro = float(getattr(cam, "ult_rostro", 0.0))
        ult_dueno = float(getattr(cam, "ult_dueno", 0.0))
        ult_ajeno = float(getattr(cam, "ult_ajeno", 0.0))
        persona_reciente = max(ult_rostro, ult_dueno, ult_ajeno)

        # ¿Se detectó a alguien en los últimos 2.5 segundos?
        if persona_reciente > 0.0 and (ahora - persona_reciente < 2.5):
            self.ult_persona = ahora

        tiempo_sin_ver = ahora - self.ult_persona
        remota_activa = self._es_remota_activa()

        if not self.ausente:
            if tiempo_sin_ver >= TIEMPO_AUSENCIA_SEGUNDOS:
                self.ausente = True
                self.tiempo_inicio_ausencia = ahora
                log(f"Estado cambiado a AUSENTE (sin personas detectadas por {int(tiempo_sin_ver)} s).")

                if remota_activa:
                    log("Pantalla remota activa: ocultando cara de laptop y activando cara grande en tablet.")
                    self.discreto_activo = True
                    self.app.cola.put(("presencia_modo_discreto", True))
                else:
                    log("Pantalla remota inactiva: estado ausente registrado sin cambios en la laptop.")
        else:
            # Está ausente: comprobar si Moisés (o alguien si no hay dueño enrolado) ha regresado
            dueno_enrolado = getattr(cam, "dueno", None) is not None
            regreso = False

            if dueno_enrolado:
                # Solo Moisés cuenta como retorno del dueño ("cuando me detecta de nuevo")
                if ult_dueno > self.tiempo_inicio_ausencia:
                    regreso = True
            else:
                if persona_reciente > self.tiempo_inicio_ausencia:
                    regreso = True

            if regreso:
                self.ausente = False
                self.ult_persona = ahora
                log("Estado cambiado a PRESENTE: dueño detectado frente a la laptop.")

                if self.discreto_activo:
                    self.discreto_activo = False
                    log("Restaurando cara de la laptop con transición suave.")
                    self.app.cola.put(("presencia_modo_discreto", False))

                    if ahora - self.ult_saludo >= INTERVALO_SALUDO_SEGUNDOS:
                        self.ult_saludo = ahora
                        saludos = [
                            "Ya volviste, Moisés.",
                            "Aquí estás de vuelta.",
                            "Ya volviste.",
                        ]
                        saludo = random.choice(saludos)
                        self.app.cola.put(("hablar", (saludo, "alegre")))
                        log(f"Saludo de regreso emitido: '{saludo}'")
                    else:
                        log("Saludo de regreso omitido (intervalo de 10 min aún activo).")
                else:
                    log("Regreso registrado (pantalla remota no estaba en modo discreto).")

    def accion_activar_presencia(self):
        """Activa la detección de presencia del dueño mediante la cámara."""
        if hasattr(self.app, "voz_dueno") and self.app.voz_dueno:
            permitido, frase = self.app.voz_dueno.autorizar_accion("activar_presencia")
            if not permitido:
                self.app.cola.put(("hablar", (frase, "calida")))
                return

        with self._bloqueo:
            self.activa = True
            self.ult_persona = time.time()
            self.tiempo_inicio_ausencia = 0.0
            datos = estado.cargar()
            datos["presencia_activa"] = True
            estado.guardar(datos)

        log("Detección de presencia activada.")
        self.app.cola.put(("hablar", "Detección de presencia activada. Vigilaré si estás frente a la laptop."))

    def accion_desactivar_presencia(self):
        """Desactiva la detección de presencia."""
        if hasattr(self.app, "voz_dueno") and self.app.voz_dueno:
            permitido, frase = self.app.voz_dueno.autorizar_accion("desactivar_presencia")
            if not permitido:
                self.app.cola.put(("hablar", (frase, "calida")))
                return

        with self._bloqueo:
            self.activa = False
            self.ausente = False
            if self.discreto_activo:
                self.discreto_activo = False
                self.app.cola.put(("presencia_modo_discreto", False))
            datos = estado.cargar()
            datos["presencia_activa"] = False
            estado.guardar(datos)

        log("Detección de presencia desactivada.")
        self.app.cola.put(("hablar", "Detección de presencia desactivada."))


def instalar(app):
    """Instala el módulo de presencia y registra sus acciones."""
    gestor = GestorPresencia(app)
    app.presencia = gestor

    acciones.registrar(
        "activar_presencia",
        lambda: gestor.accion_activar_presencia(),
        "activa la detección de presencia del usuario con la cámara para coordinar la laptop y la tablet (úsala si te piden activar presencia o vigilar si estoy aquí)",
    )
    acciones.registrar(
        "desactivar_presencia",
        lambda: gestor.accion_desactivar_presencia(),
        "desactiva la detección de presencia (úsala si te piden desactivar presencia o dejar de vigilar si estoy)",
    )

    log("Módulo de presencia instalado.")
    return gestor
