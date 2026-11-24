"""Regresión: invocación natural Lyris, sin frases hechas y con reenganche N turnos."""
import contextlib
import io
import os
import queue
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import conversacion
import eventos
import invocacion_lyris


class RespuestaDG:
    def __init__(self, codigo, texto="Lyris, abre el bloc", duracion=1.0):
        self.status_code = codigo
        self._texto, self._duracion = texto, duracion

    def json(self):
        return {"metadata": {"duration": self._duracion},
                "results": {"channels": [{"alternatives": [
                    {"transcript": self._texto}]}]}}


class CaraFalsa:
    def __init__(self):
        self.escuchando = False
        self.hablando = False

    def poner_escuchando(self, valor):
        self.escuchando = bool(valor)

    def poner_hablando(self, valor):
        self.hablando = bool(valor)

    def decir(self, texto, *_a, **_k):
        self.hablando = True
        self.ultimo_burbuja = texto

    def asentir(self, *_a):
        pass

    def fijar_emocion(self, *_a):
        pass

    def programar_retorno_neutral(self, *_a):
        pass


class TestInvocacionNatural(unittest.TestCase):
    def _app(self):
        enviados, hablado = [], []

        class OidoFalso:
            bloqueo = threading.RLock()
            ultimo_audio = None
            duracion_ultimo_audio = 0.0

            def escuchar(self, **_kw):
                return None

        app = SimpleNamespace(
            cola=queue.Queue(),
            cara=CaraFalsa(),
            memoria=SimpleNamespace(nombre="Lyris", creador="Usuario"),
            voz=SimpleNamespace(ocupada=lambda: False),
            oido=OidoFalso(),
            conversacion=False,
            escuchando=False,
            descansando=False,
            musica_activa=False,
            silencios=0,
            flujo=None,
            pendiente_descanso=False,
            _generacion_escucha=0,
            _t_accion_llm=0,
            _flujo_cerrado=False,
            _iniciar_reflexion=lambda: None,
            _es_eco=lambda _t: False,
        )
        app._dejar_de_escuchar = lambda: conversacion.dejar_de_escuchar(app)
        app.escuchar = lambda: conversacion.escuchar(app)
        app.descansar = lambda: None
        app.decir = lambda texto, **_kw: (hablado.append(texto), app.cara.decir(texto))

        def enviar(texto):
            enviados.append(texto)
            app.cara.decir(f"Respuesta: {texto}")
            app.cola.put(("fin_voz", None))

        app.enviar = enviar
        app.invocacion = invocacion_lyris.GestorInvocacion(app)
        app.invocacion.vivo = True  # bucle interior, sin hilo de micrófono real
        app.invocacion_ambiental = True
        return app, enviados, hablado

    @staticmethod
    def _drenar(app):
        while not app.cola.empty():
            tipo, valor = app.cola.get_nowait()
            if not invocacion_lyris.interceptar(app, tipo, valor):
                eventos.atender_evento(app, tipo, valor)

    @staticmethod
    def _reposo_celeste(app):
        return (not app.conversacion and not app.escuchando
                and not app.cara.escuchando and not app.cara.hablando)

    def test_lyris_inicio_medio_y_final_sin_frases_hechas(self):
        casos = [
            ("Lyris, qué hora es", "qué hora es"),
            ("Oye, cómo va la batería, Lyris", "cómo va la batería"),
            ("Por cierto Lyris dime la hora", "por cierto dime la hora"),
        ]
        for frase, orden in casos:
            with self.subTest(frase=frase):
                app, enviados, hablado = self._app()
                with patch.object(invocacion_lyris, "_sonido", lambda: None):
                    app.invocacion._procesar(frase)
                    self._drenar(app)
                self.assertEqual(enviados, [orden])
                self.assertFalse(any("Te escucho" in h or "dejo de escuchar" in h
                                     for h in hablado))
                self.assertTrue(self._reposo_celeste(app))

    def test_solo_lyris_amarillo_sin_hablar_y_espera_orden(self):
        app, enviados, hablado = self._app()
        with patch.object(invocacion_lyris, "_sonido", lambda: None):
            app.invocacion._procesar("Lyris")
            self._drenar(app)
        self.assertTrue(app.invocacion.esperando_orden)
        self.assertTrue(app.cara.escuchando)
        self.assertFalse(app.cara.hablando)
        self.assertEqual(hablado, [])
        self.assertEqual(enviados, [])

        app.invocacion._procesar("dime la hora")
        self._drenar(app)
        self.assertEqual(enviados, ["dime la hora"])
        self.assertTrue(self._reposo_celeste(app))

        # Silencio tras el nombre: vuelve a celeste sin decir nada.
        app.invocacion._procesar("Lyris")
        self._drenar(app)
        hablado.clear()
        app.invocacion.limite_orden = time.monotonic() - 1
        app.invocacion._procesar(None)
        self._drenar(app)
        self.assertFalse(app.invocacion.esperando_orden)
        self.assertEqual(hablado, [])
        self.assertTrue(self._reposo_celeste(app))

    def test_frase_sin_lyris_en_reposo_se_ignora(self):
        app, enviados, hablado = self._app()
        app.invocacion._procesar("hola mundo, qué tal el clima")
        self._drenar(app)
        self.assertEqual(enviados, [])
        self.assertEqual(hablado, [])
        self.assertFalse(app.cara.escuchando)
        self.assertTrue(self._reposo_celeste(app))
        self.assertTrue(app.invocacion._puede_capturar())

    def test_tres_turnos_consecutivos_sin_trabarse(self):
        app, enviados, _hablado = self._app()
        with patch.object(invocacion_lyris, "_sonido", lambda: None):
            for turno in range(3):
                frase = f"Lyris, dime la hora {turno}"
                app.invocacion._procesar(frase)
                self._drenar(app)
                self.assertEqual(len(enviados), turno + 1)
                self.assertEqual(enviados[-1], f"dime la hora {turno}")
                self.assertFalse(app.invocacion.en_turno)
                self.assertFalse(app.invocacion.esperando_orden)
                self.assertTrue(app.invocacion.activo)
                self.assertTrue(app.invocacion._puede_capturar())
                self.assertTrue(self._reposo_celeste(app))

    def test_silenciador_pausa_y_reanuda_escucha_ambiental(self):
        app, _enviados, _hablado = self._app()
        with patch.object(invocacion_lyris.GestorInvocacion, "iniciar", lambda self: None):
            self.assertTrue(conversacion.alternar_silencio(app))
            self.assertFalse(app.invocacion.activo)
            self.assertFalse(app.invocacion_ambiental)
            self.assertFalse(app.invocacion._puede_capturar())
            self.assertTrue(self._reposo_celeste(app))

            self.assertFalse(conversacion.alternar_silencio(app))
            self.assertTrue(app.invocacion.activo)
            self.assertTrue(app.invocacion_ambiental)
            self.assertTrue(app.invocacion._puede_capturar())

    def test_confusiones_foneticas_y_vocativo_luis_serious(self):
        sonidos = []
        casos = [
            ("Luis ¿Cómo va la laptop?", "luis", "cómo va la laptop"),
            ("¿Cómo va la laptop, Luis?", "luis", "cómo va la laptop"),
            ("Serious, dime la hora", "serious", "dime la hora"),
            ("Iris, dime la hora", "iris", "dime la hora"),
            ("Lyra, dime la hora", "lyra", "dime la hora"),
            ("Liria, dime la hora", "liria", "dime la hora"),
            ("Siris, dime la hora", "siris", "dime la hora"),
            ("Lyries, dime la hora", "lyries", "dime la hora"),
        ]
        with patch.object(invocacion_lyris, "_sonido", lambda: sonidos.append(1)), \
                contextlib.redirect_stdout(io.StringIO()) as salida:
            for frase, variante, orden in casos:
                with self.subTest(frase=frase):
                    sonidos.clear()
                    app, enviados, _hablado = self._app()
                    app.invocacion._procesar(frase)
                    self._drenar(app)
                    self.assertEqual(enviados, [orden])
                    self.assertEqual(len(sonidos), 1)
                    self.assertIn(
                        f"[invocacion] detectada='{variante}' -> orden='{orden}'",
                        salida.getvalue())

            # "Serious." solo: amarillo, sin orden ni locución.
            sonidos.clear()
            app, enviados, _hablado = self._app()
            app.invocacion._procesar("Serious.")
            self._drenar(app)
            self.assertTrue(app.invocacion.esperando_orden)
            self.assertEqual(enviados, [])
            self.assertEqual(len(sonidos), 1)

            # Narrativa con Luis en medio: se ignora sin sonido ni disparo.
            sonidos.clear()
            app, enviados, _hablado = self._app()
            app.invocacion._procesar("Conocí a Luis ayer en clase")
            self._drenar(app)
            self.assertEqual(enviados, [])
            self.assertEqual(sonidos, [])
            self.assertTrue(self._reposo_celeste(app))
            self.assertTrue(app.invocacion._puede_capturar())

    def test_impulso_keyterm_en_deepgram_y_reintento_sin_el(self):
        import oido_deepgram
        oido_deepgram.reiniciar()
        self.addCleanup(oido_deepgram.reiniciar)
        parches = [
            patch.object(oido_deepgram.config, "DEEPGRAM_API_KEY", "", create=True),
            patch.object(oido_deepgram.config, "DEEPGRAM_MODEL", "", create=True),
            patch.dict(os.environ, {"DEEPGRAM_API_KEY": "prueba-keyterm",
                                    "DEEPGRAM_MODEL": "nova-3"}),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)

        with patch.object(oido_deepgram.httpx, "post",
                          Mock(return_value=RespuestaDG(200))) as post:
            resultado = oido_deepgram.transcribir(b"RIFFfalso")
        self.assertEqual(resultado[0], "Lyris, abre el bloc")
        self.assertEqual(post.call_args.kwargs["params"]["model"], "nova-3")
        self.assertEqual(post.call_args.kwargs["params"]["keyterm"], "Lyris:5")

        post = Mock(side_effect=[RespuestaDG(400), RespuestaDG(200)])
        with patch.object(oido_deepgram.httpx, "post", post):
            resultado = oido_deepgram.transcribir(b"RIFFfalso")
        self.assertEqual(resultado[0], "Lyris, abre el bloc")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[0].kwargs["params"]["keyterm"], "Lyris:5")
        self.assertNotIn("keyterm", post.call_args_list[1].kwargs["params"])
        self.assertTrue(oido_deepgram.esta_activo())

    def test_instalar_apaga_vosk_y_filtro_campp(self):
        app, _enviados, _hablado = self._app()
        detenido = []
        app.palabra_clave = SimpleNamespace(
            detener=lambda: detenido.append(True), vivo=True)
        with patch.object(invocacion_lyris.GestorInvocacion, "iniciar", lambda self: None):
            gestor = invocacion_lyris.instalar(app)
        self.assertEqual(detenido, [True])
        self.assertTrue(gestor.activo)
        self.assertTrue(app.invocacion_ambiental)

        vd = SimpleNamespace(activa=True, modo_solo_dueno=True,
                             ultima_verificacion={"es_dueno": False},
                             evaluar_entrada_voz=lambda _t: None)
        app.voz_dueno = vd
        self.assertFalse(invocacion_lyris.permitir_transcripcion(app))
        vd.ultima_verificacion = {"es_dueno": True}
        self.assertTrue(invocacion_lyris.permitir_transcripcion(app))


if __name__ == "__main__":
    unittest.main()
