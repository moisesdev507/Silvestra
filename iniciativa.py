"""Módulo de iniciativa espontánea para Silvestra."""
import os
import threading
import time

import acciones
import estado
import hilos


class Iniciativa:
    def __init__(self, app):
        self.app = app
        self.activa = estado.cargar().get("iniciativa", False)
        self.ultima_iniciativa = 0.0
        self.ultima_interaccion_usuario = time.time()

    def interaccion(self):
        """Registra que el usuario acaba de interactuar."""
        self.ultima_interaccion_usuario = time.time()

    def activar(self):
        self.activa = True
        est = estado.cargar()
        est["iniciativa"] = True
        estado.guardar(est)
        self.app.cara.decir("Iniciativa activada.", 3000)

    def desactivar(self):
        self.activa = False
        est = estado.cargar()
        est["iniciativa"] = False
        estado.guardar(est)
        self.app.cara.decir("Iniciativa desactivada.", 3000)

    def revisar(self):
        """Verifica periódicamente si se cumplen las condiciones para hablar con iniciativa."""
        try:
            ahora = time.time()
            hora = time.localtime().tm_hour
            # Condiciones: activa, no descansando, hora entre 7am y 11pm, 20 min inactividad, 45 min cooldown
            if (
                self.activa
                and not self.app.descansando
                and 7 <= hora < 23
                and ahora - self.ultima_interaccion_usuario >= 1200
                and ahora - self.ultima_iniciativa >= 2700
                and self.app.puede_hablar_sola()
            ):
                estudio_libre = True
                if hasattr(self.app, "estudio"):
                    if self.app.estudio.en_examen() or self.app.estudio.timer_id is not None:
                        estudio_libre = False
                if estudio_libre:
                    threading.Thread(target=self._hablar, daemon=True).start()
        except Exception:
            pass
        self.app.cara.root.after(30000, self.revisar)

    def _hablar(self):
        try:
            import memoria_tiempo as mt
            hechos_fmt = [mt.formatear_recuerdo_con_fecha(h) for h in self.app.memoria.hechos]
            hechos = "\n".join(f"- {h}" for h in hechos_fmt) or "- (ninguno)"
            sistema = (
                f"Eres {self.app.memoria.nombre or 'Silvestra'}, asistente de {self.app.memoria.creador or 'tu creador'}.\n"
                "Llevan más de 20 minutos en silencio y quieres hablarle con iniciativa propia de forma espontánea.\n"
                f"Hechos que recuerdas (con su antigüedad):\n{hechos}\n"
                f"Hilos y temas pendientes:\n{hilos.resumen()}\n\n"
                "Di UNA sola frase corta y natural (un comentario amistoso o una pregunta sencilla basada en un hilo pendiente o en algo que recuerdes de él).\n"
                "Reglas:\n"
                "1. Máximo 15 a 20 palabras.\n"
                "2. Tono panameño suave y cercano, sin sonar invasiva ni robot.\n"
                "3. Si un evento en los recuerdos ya pasó según su fecha, PROHIBIDO preguntar por él en futuro.\n"
                "4. Sin asteriscos, sin listas, sin comillas, sin emojis.\n"
                "Responde ÚNICAMENTE con la frase que dirás en voz alta."
            )
            frase = self.app.cerebro._pedir([
                {"role": "system", "content": sistema},
                {"role": "user", "content": "Genera tu comentario espontáneo."},
            ])
            limpio = frase.replace("*", "").replace("\n", " ").strip("\"' ")
            if limpio:
                self.ultima_iniciativa = time.time()
                if hasattr(self.app, "cola") and self.app.cola:
                    self.app.cola.put(("hablar", (limpio, "calida")))
        except Exception as e:
            print(f"[iniciativa] Error generando comentario: {e}", flush=True)


def instalar(app):
    ini = Iniciativa(app)
    acciones.registrar(
        "activar_iniciativa",
        ini.activar,
        "activa la iniciativa propia para que Silvestra hable de vez en cuando si llevan mucho tiempo en silencio.",
    )
    acciones.registrar(
        "desactivar_iniciativa",
        ini.desactivar,
        "desactiva la iniciativa propia para que Silvestra no hable de forma espontánea.",
    )
    app.cara.root.after(30000, ini.revisar)
    return ini
