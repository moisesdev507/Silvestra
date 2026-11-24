"""Regresión: invocación natural Lyris y captura en dos tiempos."""
import contextlib
import io
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import conversacion
import eventos
import invocacion_lyris
from invocacion_pruebas import fabricar_app


class TestInvocacionNatural(unittest.TestCase):
    def _app(self):
        return fabricar_app()

    def setUp(self):
        self.voces = []
        for nombre, objetivo in (("_sonido", lambda *_a: None),
                                 ("_micro_voz", lambda app: self.voces.append(app))):
            p = patch.object(invocacion_lyris, nombre, objetivo)
            p.start()
            self.addCleanup(p.stop)

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
            ("Haciendo venda ustedes, Lyris. Después. ¿Y el núcleo?",
             "después y el núcleo"),
            ("Oye, cómo va la batería, Lyris", ""),
            ("Por cierto Lyris dime la hora", "dime la hora"),
        ]
        for frase, orden in casos:
            with self.subTest(frase=frase):
                app, enviados, hablado = self._app()
                with patch.object(invocacion_lyris, "_sonido", lambda *_a: None):
                    app.invocacion._procesar(frase)
                    self._drenar(app)
                self.assertEqual(enviados, [orden] if orden else [])
                if not orden:
                    self.assertTrue(app.invocacion.esperando_orden)
                self.assertFalse(any("Te escucho" in h or "dejo de escuchar" in h
                                     for h in hablado))
                if orden:
                    self.assertTrue(self._reposo_celeste(app))

    def test_solo_lyris_amarillo_sin_hablar_y_espera_orden(self):
        app, enviados, hablado = self._app()
        with patch.object(invocacion_lyris, "_sonido", lambda *_a: None):
            app.invocacion._procesar("Lyris")
            self._drenar(app)
        self.assertTrue(app.invocacion.esperando_orden)
        self.assertTrue(app.cara.escuchando)
        self.assertFalse(app.cara.hablando)
        self.assertEqual(hablado, [])
        self.assertEqual(enviados, [])
        self.assertEqual(len(self.voces), 1)  # micro-voz «¿Sí?» en vez de pitido

        app.invocacion._procesar("dime la hora")
        self._drenar(app)
        self.assertEqual(enviados, ["dime la hora"])
        self.assertTrue(self._reposo_celeste(app))

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
        self.assertTrue(self._reposo_celeste(app))

    def test_tres_turnos_consecutivos_sin_trabarse(self):
        app, enviados, _hablado = self._app()
        with patch.object(invocacion_lyris, "_sonido", lambda *_a: None):
            for turno in range(3):
                frase = f"Lyris, dime la hora {turno}"
                app.invocacion._procesar(frase)
                self._drenar(app)
                self.assertEqual(enviados,
                                 [f"dime la hora {i}" for i in range(turno + 1)])
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
            ("¿Cómo va la laptop, Luis?", "luis", ""),
            ("Serious, dime la hora", "serious", "dime la hora"),
            ("Iris, dime la hora", "iris", "dime la hora"),
            ("Lyra, dime la hora", "lyra", "dime la hora"),
            ("Liria, dime la hora", "liria", "dime la hora"),
            ("Siris, dime la hora", "siris", "dime la hora"),
            ("Lyries, dime la hora", "lyries", "dime la hora"),
        ]
        with patch.object(invocacion_lyris, "_sonido",
                          lambda nombre="activar": sonidos.append(nombre)), \
                contextlib.redirect_stdout(io.StringIO()) as salida:
            for frase, variante, orden in casos:
                with self.subTest(frase=frase):
                    sonidos.clear()
                    self.voces.clear()
                    app, enviados, _hablado = self._app()
                    app.invocacion._procesar(frase)
                    self._drenar(app)
                    self.assertEqual(enviados, [orden] if orden else [])
                    if not orden:
                        self.assertTrue(app.invocacion.esperando_orden)
                    self.assertEqual((sonidos, len(self.voces)),
                                     ([], 1 if not orden else 0))
                    self.assertIn(
                        f"[invocacion] detectada='{variante}' -> orden='{orden}'",
                        salida.getvalue())

            sonidos.clear()
            app, enviados, _hablado = self._app()
            app.invocacion._procesar("Serious.")
            self._drenar(app)
            self.assertTrue(app.invocacion.esperando_orden)
            self.assertEqual(enviados, [])
            self.assertEqual((sonidos, len(self.voces)), ([], 1))

            sonidos.clear()
            self.voces.clear()
            app, enviados, _hablado = self._app()
            app.invocacion._procesar("Conocí a Luis ayer en clase")
            self._drenar(app)
            self.assertEqual(enviados, [])
            self.assertEqual((sonidos, self.voces), ([], []))
            self.assertTrue(self._reposo_celeste(app))
            self.assertTrue(app.invocacion._puede_capturar())

    def test_orden_dos_tiempos_y_eco_corto(self):
        self.assertEqual((invocacion_lyris.TIEMPO_ORDEN,
                          invocacion_lyris.DURACION_ECO), (20.0, 0.4))
        app, enviados, _ = self._app()
        sonidos = []
        with patch.object(invocacion_lyris, "_sonido",
                          lambda nombre="activar": sonidos.append(nombre)):
            app.invocacion._procesar("Lyris.")
            self._drenar(app)
            self.assertEqual((sonidos, len(self.voces)), ([], 1))
            self.assertTrue(app.invocacion.esperando_orden)
            self.assertTrue(app.cara.escuchando)
            self.assertAlmostEqual(app.invocacion.limite_orden - time.monotonic(),
                                   20.0, delta=0.3)
            app.invocacion._procesar("mm", duracion=0.2)  # eco: no cierra
            self._drenar(app)
            self.assertTrue(app.invocacion.esperando_orden)
            self.assertEqual(enviados, [])
            orden = "¿Puedes revisar cómo va la laptop, por favor?"
            app.invocacion._procesar(orden)
            self._drenar(app)
        self.assertEqual((enviados, sonidos, len(self.voces)), ([orden], [], 1))
        self.assertTrue(self._reposo_celeste(app))

    def test_confirmar_junto_y_ventana_continua(self):
        app, enviados, _ = self._app()
        sonidos = []
        with patch.object(invocacion_lyris, "_sonido",
                          lambda nombre="activar": sonidos.append(nombre)):
            app.invocacion._procesar("Lyris, ¿cómo va la laptop?")
            self._drenar(app)
            app.invocacion._procesar("Hoy hace mucho sol en la ventana")
            self._drenar(app)
        self.assertEqual((enviados, sonidos, self.voces),
                         (["cómo va la laptop", "Hoy hace mucho sol en la ventana"],
                          [], []))
        self.assertTrue(self._reposo_celeste(app))

    def test_evento_oido_en_espera_es_orden(self):
        app, enviados, _ = self._app()
        with patch.object(invocacion_lyris, "_sonido", lambda *_a: None):
            app.invocacion._procesar("Oye Lyris")
            self._drenar(app)
            self.assertTrue(invocacion_lyris.interceptar(app, "oido", "revisa la batería"))
            self._drenar(app)
        self.assertEqual(enviados, ["revisa la batería"])
        self.assertTrue(self._reposo_celeste(app))

    def test_sin_respuesta_hablada_vuelve_a_celeste(self):
        app, enviados, _hablado = self._app()
        app.enviar = lambda texto: enviados.append(texto)  # nunca llega fin_voz
        with patch.object(invocacion_lyris, "_sonido", lambda *_a: None):
            app.invocacion._procesar("Lyris, revisa el estado")
            self._drenar(app)
        self.assertEqual(len(enviados), 1)
        self.assertTrue(app.invocacion.en_turno)

        app.invocacion.limite_respuesta = time.monotonic() - 1
        self.assertFalse(app.invocacion._puede_capturar())
        self._drenar(app)
        self.assertFalse(app.invocacion.en_turno)
        self.assertTrue(self._reposo_celeste(app))
        self.assertTrue(app.invocacion._puede_capturar())

    def test_orden_garabateada_no_enviada_y_vuelve_a_celeste(self):
        app, enviados, _hablado = self._app()
        garabateo = "Lyris, qué hora es, qué hora es, cuándo es, cuándo es"
        with patch.object(invocacion_lyris, "_sonido", lambda *_a: None):
            app.invocacion._procesar(garabateo)
            self._drenar(app)
        self.assertEqual(enviados, [])
        self.assertFalse(app.invocacion.en_turno)
        self.assertTrue(self._reposo_celeste(app))

    def test_instalar_apaga_vosk_y_filtro_campp(self):
        app, _, _ = self._app()
        detenido = []
        app.palabra_clave = SimpleNamespace(detener=lambda: detenido.append(True))
        with patch.object(invocacion_lyris.GestorInvocacion, "iniciar", lambda s: None):
            gestor = invocacion_lyris.instalar(app)
        self.assertEqual((detenido, gestor.activo, app.invocacion_ambiental),
                         ([True], True, True))

        vd = SimpleNamespace(activa=True, modo_solo_dueno=True,
                             ultima_verificacion={"es_dueno": False},
                             evaluar_entrada_voz=lambda _t: None)
        app.voz_dueno = vd
        self.assertFalse(invocacion_lyris.permitir_transcripcion(app))
        vd.ultima_verificacion = {"es_dueno": True}
        self.assertTrue(invocacion_lyris.permitir_transcripcion(app))

    def test_variantes_iniciales_ampliadas(self):
        casos = (("Lirys, dime la hora", "lirys"), ("Lyres, dime la hora", "lyres"),
                 ("Lirez, dime la hora", "lirez"))
        for frase, variante in casos:
            with self.subTest(frase=frase):
                app, enviados, _ = self._app()
                with contextlib.redirect_stdout(io.StringIO()) as salida:
                    app.invocacion._procesar(frase)
                    self._drenar(app)
                self.assertEqual(enviados, ["dime la hora"])
                self.assertIn(f"detectada='{variante}'", salida.getvalue())

    def test_modo_directo_sin_palabra_clave_con_campp(self):
        app, enviados, _ = self._app()
        app.invocacion.palabra_clave = False
        app.voz_dueno = SimpleNamespace(
            activa=True, modo_solo_dueno=True,
            ultima_verificacion={"es_dueno": True},
            evaluar_entrada_voz=lambda _t: None)
        app.invocacion._procesar("dime la hora por favor")
        self._drenar(app)
        self.assertEqual(enviados, ["dime la hora por favor"])
        app.voz_dueno.ultima_verificacion = {"es_dueno": False}
        app.invocacion._procesar("esto no debe pasar")
        self._drenar(app)
        self.assertEqual(enviados, ["dime la hora por favor"])

    def test_ventana_seguimiento_18s_tras_respuesta(self):
        self.assertEqual(invocacion_lyris.TIEMPO_SEGUIMIENTO, 18.0)
        app, enviados, _ = self._app()
        app.invocacion._procesar("Lyris, dime la hora")
        self._drenar(app)
        self.assertTrue(app.invocacion.seguimiento_activo)
        self.assertAlmostEqual(app.invocacion.limite_seguimiento - time.monotonic(),
                               18.0, delta=0.3)
        self.assertTrue(self._reposo_celeste(app))
        app.invocacion._procesar("y ahora cuál es la fecha")
        self._drenar(app)
        self.assertEqual(enviados[-1], "y ahora cuál es la fecha")
        app.invocacion.limite_seguimiento = time.monotonic() - 1
        app.invocacion._puede_capturar()
        self.assertFalse(app.invocacion.seguimiento_activo)
        app.invocacion._procesar("ya no debe pasar")
        self._drenar(app)
        self.assertEqual(enviados, ["dime la hora", "y ahora cuál es la fecha"])

if __name__ == "__main__":
    unittest.main()
