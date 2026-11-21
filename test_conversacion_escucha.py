"""Regresiones de escucha al alternar conversación y cancelar locuciones."""
import queue
import threading
import time
import unittest

from conversacion import alternar_conversacion
from voz import Flujo, Voz
from oido import Oido


class TestReanudacionEscucha(unittest.TestCase):
    def test_alternar_con_tts_interrumpido_reanuda_captura(self):
        oido = object.__new__(Oido)
        oido.bloqueo = threading.RLock()
        oido._escuchando_activo = False
        primera = threading.Event()
        llamadas = []

        def capturar(corto=False, app=None, generacion=None):
            llamadas.append(generacion)
            if len(llamadas) == 1:
                primera.set()
                while app._generacion_escucha == generacion:
                    time.sleep(0.005)
                return None
            return "audio listo"

        oido._escuchar = capturar
        app = type("App", (), {})()
        app.memoria = type("Memoria", (), {"nombre": "Usuario"})()
        app.cara = type("Cara", (), {"poner_escuchando": lambda *args: None})()
        app.oido = oido
        app.cola = queue.Queue()
        app.conversacion = False
        app.escuchando = False
        app._generacion_escucha = 0
        app.silencios = 0
        app.musica_activa = False
        app._iniciar_reflexion = lambda: None
        app.locuciones = []

        def decir(frase, *args, **kwargs):
            if app.locuciones:
                app.locuciones[-1] = "interrumpida"
            app.locuciones.append(frase)

        app.decir = decir
        alternar_conversacion(app, "prueba_inicio")
        self.assertTrue(primera.wait(1.0))
        alternar_conversacion(app, "prueba_silencio")
        alternar_conversacion(app, "prueba_reanudar")

        limite = time.time() + 2.0
        while app.cola.empty() and time.time() < limite:
            time.sleep(0.01)
        self.assertEqual(app.cola.get_nowait(), ("oido", "audio listo"))
        self.assertTrue(app.conversacion)
        self.assertTrue(app.escuchando)
        self.assertEqual(llamadas, [1, 3])
        self.assertIn("interrumpida", app.locuciones)

    def test_final_de_tts_obsoleto_no_decrementa_el_nuevo(self):
        voz = object.__new__(Voz)
        voz.version = 1
        voz._activos = 1
        voz._estado_lock = threading.RLock()
        voz.nivel_volumen = 0.5
        voz._parar = lambda: None
        flujo = Flujo()
        hilo = threading.Thread(target=voz._hablar, args=(flujo, None, 1))
        hilo.start()
        time.sleep(0.05)
        with voz._estado_lock:
            voz.version = 2
            voz._activos = 1
        flujo.cerrar()
        hilo.join(1.0)
        self.assertFalse(hilo.is_alive())
        self.assertEqual(voz._activos, 1)


if __name__ == "__main__":
    unittest.main()
