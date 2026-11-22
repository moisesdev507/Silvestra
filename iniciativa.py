"""Módulo de iniciativa espontánea para Silvestra (Evolucionado con Etapa 5)."""
from __future__ import annotations

import os
import threading
import time
from typing import Any

import acciones
import estado
import hilos
import iniciativa_contextual


class Iniciativa:
    def __init__(self, app: Any):
        self.app = app
        self.activa = estado.cargar().get("iniciativa", False)
        self.motor = iniciativa_contextual.obtener_motor_iniciativa()
        self.ultima_iniciativa = 0.0
        self.ultima_interaccion_usuario = time.time()

    def interaccion(self) -> None:
        """Registra que el usuario acaba de interactuar."""
        self.ultima_interaccion_usuario = time.time()
        self.motor.registrar_interaccion_usuario(self.ultima_interaccion_usuario)

    def activar(self) -> None:
        self.activa = True
        est = estado.cargar()
        est["iniciativa"] = True
        estado.guardar(est)
        self.app.cara.decir("Iniciativa activada.", 3000)

    def desactivar(self) -> None:
        self.activa = False
        est = estado.cargar()
        est["iniciativa"] = False
        estado.guardar(est)
        self.app.cara.decir("Iniciativa desactivada.", 3000)

    def revisar(self) -> None:
        """Verifica periódicamente mediante el motor contextual si Silvestra debe hablar."""
        hubo_iniciativa = False
        try:
            if self.activa:
                sug = self.motor.evaluar_oportunidad(self.app)
                if sug is not None:
                    hubo_iniciativa = True
                    threading.Thread(target=self._hablar, args=(sug,), daemon=True).start()
        except Exception as e:
            print(f"[iniciativa] Error en revisión contextual: {e}", flush=True)

        if not hubo_iniciativa:
            try:
                import cerebro_proactivo
                cerebro_proactivo.evaluar_proactividad(self.app, motivo="periodico")
            except Exception:
                pass

        if hasattr(self.app, "cara") and hasattr(self.app.cara, "root"):
            self.app.cara.root.after(30000, self.revisar)

    def _hablar(self, sug: Any) -> None:
        """Sintetiza y emite la iniciativa guiada por el contexto."""
        try:
            if getattr(self.app, "hablando", False):
                return
            cola = getattr(self.app, "cola", None)
            if cola:
                try:
                    q = getattr(cola, "queue", [])
                    if any(isinstance(it, tuple) and it and it[0] == "hablar" for it in q):
                        return
                except Exception:
                    pass

            try:
                import cerebro_proactivo
                m_pro = cerebro_proactivo.obtener_motor_proactivo()
                if (time.time() - m_pro.ultimo_aviso) < 300.0:
                    return
            except Exception:
                pass

            valido, motivo = self.motor.revalidar_sugerencia(sug, self.app)
            if not valido:
                return

            guia = getattr(sug, "prompt_orientacion", "Llevan más de 20 minutos en silencio.")
            hechos = "- (ninguno)"
            memoria = getattr(self.app, "memoria", None)
            if memoria and hasattr(memoria, "recuperar"):
                import memoria_recuperacion
                paquete = memoria.recuperar(guia, contexto=guia, limite=3)
                hechos = memoria_recuperacion.formatear(paquete, 650) or hechos
            nombre_asistente = getattr(self.app.memoria, "nombre", None) or "Silvestra"
            creador = getattr(self.app.memoria, "creador", None) or "tu creador"

            sistema = (
                f"Eres {nombre_asistente}, asistente de {creador}.\n"
                f"Contexto situacional: {guia}\n"
                f"Hechos que recuerdas (con su antigüedad):\n{hechos}\n"
                f"Hilos y temas pendientes:\n{hilos.resumen()}\n\n"
                "Di UNA sola frase corta y natural (un comentario amistoso o pregunta sencilla).\n"
                "Reglas:\n"
                "1. Máximo 15 a 20 palabras.\n"
                "2. Tono panameño suave y cercano, sin sonar invasiva ni robot.\n"
                "3. Si un evento en recuerdos ya pasó según su fecha, PROHIBIDO preguntar por él en futuro.\n"
                "4. Sin asteriscos, sin listas, sin comillas, sin emojis.\n"
                "Responde ÚNICAMENTE con la frase que dirás en voz alta."
            )
            frase = self.app.cerebro._pedir([
                {"role": "system", "content": sistema},
                {"role": "user", "content": "Genera tu comentario espontáneo."},
            ])
            limpio = str(frase or "").replace("*", "").replace("\n", " ").strip("\"' ")
            if limpio:
                valido_post, _ = self.motor.revalidar_sugerencia(sug, self.app)
                if not valido_post:
                    return

                self.motor.marcar_emitida(sug)
                self.ultima_iniciativa = time.time()
                try:
                    import cerebro_proactivo
                    cerebro_proactivo.obtener_motor_proactivo().ultimo_aviso = time.time()
                except Exception:
                    pass
                emocion = getattr(sug, "emocion_sugerida", "calida")
                if hasattr(self.app, "cola") and self.app.cola:
                    self.app.cola.put(("hablar", (limpio, emocion)))
        except Exception as e:
            print(f"[iniciativa] Error generando comentario: {e}", flush=True)


def instalar(app: Any) -> Iniciativa:
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
    if hasattr(app, "cara") and hasattr(app.cara, "root"):
        app.cara.root.after(30000, ini.revisar)
    return ini
