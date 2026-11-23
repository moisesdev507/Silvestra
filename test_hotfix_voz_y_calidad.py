"""Pruebas del Bloque 0: gracia de voz, filtro de calidad y respuesta hablada."""
import time
import unittest
from unittest.mock import patch

import numpy as np

import calidad_respuesta
import eventos
import eventos_dialogo
import proveedores_cadenas as pc
import voz_dueno
import voz_gracia


class _Oido:
    ultimo_audio = object()

    def __init__(self, duracion):
        self.duracion_ultimo_audio = duracion


class _AppVoz:
    def __init__(self, duracion):
        self.oido = _Oido(duracion)


def _verificador(duracion=0.53):
    vd = object.__new__(voz_dueno.VozDueno)
    vd.app = _AppVoz(duracion)
    vd.activa = True
    vd.banco_dueno = object()
    vd.umbral = 0.35
    vd.modo_solo_dueno = True
    vd.ultima_verificacion = {"es_dueno": False, "similitud": 0.0, "motivo": "inicial"}
    vd._ultima_verificacion_ok_ts = 0.0
    vd._ultima_pregunta_ts = 0.0
    vd._ultimo_embedding = None
    return vd


class TestVozGracia(unittest.TestCase):
    def test_confirmaciones_breves_y_ordenes_largas(self):
        for texto in ("Sí.", "dale", "ok", "claro", "Sí, dale"):
            self.assertTrue(voz_gracia.es_confirmacion_breve(texto), texto)
        for texto in ("Si, busca en Youtube", "Hola, ¿cómo estás?", ""):
            self.assertFalse(voz_gracia.es_confirmacion_breve(texto), texto)

    def test_conceder_exige_ventana_confirmacion_y_audio_corto(self):
        ahora = time.time()
        self.assertEqual(
            voz_gracia.conceder(ahora - 5, 0, "Sí.", 0.53, ahora=ahora),
            "gracia_verificacion_reciente",
        )
        self.assertEqual(
            voz_gracia.conceder(0, ahora - 5, "Dale", 1.1, ahora=ahora),
            "gracia_pregunta_confirmacion",
        )
        self.assertIsNone(voz_gracia.conceder(ahora - 5, 0, "Sí.", 1.9, ahora=ahora))
        self.assertIsNone(voz_gracia.conceder(ahora - 5, 0, "Busca eso", 0.5, ahora=ahora))
        self.assertIsNone(voz_gracia.conceder(ahora - 90, ahora - 90, "Sí.", 0.5, ahora=ahora))

    def test_si_tras_pregunta_se_acepta_sin_camara(self):
        vd = _verificador()
        vd.registrar_pregunta()
        vd.evaluar_entrada_voz("Sí.")
        self.assertTrue(vd.ultima_verificacion["es_dueno"])
        self.assertEqual(vd.ultima_verificacion["motivo"], "gracia_pregunta_confirmacion")

    def test_confirmacion_tras_verificacion_reciente(self):
        vd = _verificador()
        vd._ultima_verificacion_ok_ts = time.time() - 4
        vd.evaluar_entrada_voz("Dale")
        self.assertTrue(vd.ultima_verificacion["es_dueno"])
        self.assertEqual(vd.ultima_verificacion["motivo"], "gracia_verificacion_reciente")

    def test_invitado_real_sigue_bloqueado_fuera_de_ventana(self):
        vd = _verificador()
        vd.evaluar_entrada_voz("Sí.")
        self.assertFalse(vd.ultima_verificacion["es_dueno"])
        self.assertIn("audio_corto", vd.ultima_verificacion["motivo"])

        vd = _verificador()
        vd._ultima_verificacion_ok_ts = time.time() - 3
        vd.evaluar_entrada_voz("Hola, ¿cómo estás?")
        self.assertFalse(vd.ultima_verificacion["es_dueno"])

    def test_audio_largo_no_recibe_gracia_aunque_haya_verificacion_reciente(self):
        vd = _verificador(duracion=1.9)
        vd._ultima_verificacion_ok_ts = time.time() - 3
        with patch("voz_dueno.preparar_audio_biometria", return_value=(object(), 1.5)), \
             patch("voz_dueno.extraer_embedding", return_value=np.zeros(3, dtype=np.float32)), \
             patch("voz_dueno.calcular_similitud_banco", return_value=(0.01, 0.01, 2)):
            vd.evaluar_entrada_voz("Sí.")
        self.assertFalse(vd.ultima_verificacion["es_dueno"])
        self.assertEqual(vd.ultima_verificacion["motivo"], "rechazado")


class TestCalidadRespuesta(unittest.TestCase):
    def test_str_y_tokens_tecnicos_no_son_corruptos(self):
        for token in ("str", "txt", "http", "json", "pdf"):
            self.assertFalse(calidad_respuesta.es_token_corrupto(token), token)
        self.assertTrue(calidad_respuesta.analizar_calidad_texto(
            "El tipo str aparece en Python.")[0])

    def test_palabras_espanolas_con_consonantes_no_son_corruptas(self):
        for token in ("instrucciones", "transcribir", "construccion"):
            self.assertFalse(calidad_respuesta.es_token_corrupto(token), token)
        self.assertTrue(calidad_respuesta.analizar_calidad_texto(
            "Sigue las instrucciones para transcribir el texto.")[0])

    def test_corruptos_reales_se_siguen_detectando(self):
        self.assertTrue(calidad_respuesta.es_token_corrupto("sgjkdcb"))
        self.assertTrue(calidad_respuesta.es_token_corrupto("qwrty"))


class _Cara:
    def __init__(self):
        self.llamadas = []

    def fijar_emocion(self, emocion):
        pass

    def decir(self, texto, ms=None, emocion=None):
        self.llamadas.append(texto)


class _Flujo:
    def __init__(self):
        self.cerrado = False

    def cerrar(self):
        self.cerrado = True


class _AppEventos:
    def __init__(self, n_frases=0):
        self.flujo = _Flujo()
        self._frases_flujo_emitidas = n_frases
        self.cara = _Cara()
        self.ultimo_dicho = ""
        self.dicho = []
        self._ecosistema_origen = None
        self.conversacion = True
        self.origen_entrada_actual = "microfono"

    def decir(self, texto, ms=None, con_voz=True, emocion=None):
        self.dicho.append((texto, con_voz))

    def _dejar_de_escuchar(self):
        pass


class TestRespuestaHablada(unittest.TestCase):
    def test_flujo_sin_frases_hace_hablar_la_respuesta(self):
        app = _AppEventos(n_frases=0)
        eventos.atender_evento(app, "respuesta", ("Listo, ya lo busqué.", None, "neutral"))
        self.assertEqual(len(app.dicho), 1)
        self.assertEqual(app.dicho[0][0], "Listo, ya lo busqué.")
        self.assertTrue(app.dicho[0][1])
        self.assertIsNone(app.flujo)
        self.assertEqual(app.cara.llamadas, [])

    def test_flujo_con_frases_no_duplica_voz(self):
        app = _AppEventos(n_frases=1)
        eventos.atender_evento(app, "respuesta", ("Listo, ya lo busqué.", None, "neutral"))
        self.assertEqual(app.dicho, [])
        self.assertEqual(app.cara.llamadas, ["Listo, ya lo busqué."])

    def test_fallo_en_conversacion_por_voz_si_habla(self):
        app = _AppEventos()
        eventos_dialogo.atender_resto(app, "fallo", "No pude conectar", lambda _t: False)
        self.assertEqual(app.dicho[-1], ("No pude conectar", True))

    def test_fallo_fuera_de_conversacion_sigue_silencioso(self):
        app = _AppEventos()
        app.conversacion = False
        eventos_dialogo.atender_resto(app, "fallo", "No pude conectar", lambda _t: False)
        self.assertEqual(app.dicho[-1], ("No pude conectar", False))


class TestCadenasGoogle(unittest.TestCase):
    def _prov(self):
        return {
            "nombre": "Google",
            "modelos": [
                "gemini-flash-lite-latest", "gemini-flash-latest", "gemini-pro-latest",
            ],
        }

    def test_carril_rapido_usa_un_solo_modelo_sano(self):
        salud = {"tasa_error": 0.0, "ts_fallo": 0.0, "ewma_ttft": None}
        with patch("proveedores_validador.esta_desactivado", return_value=False), \
             patch("proveedores_salud.obtener_salud", return_value=salud):
            mods = pc.obtener_modelos_tarea(self._prov(), "charla", carril="rapido")
        self.assertEqual(len(mods), 1)
        self.assertIn(mods[0], pc.MODELOS_RAPIDOS_GOOGLE)
        self.assertNotIn("gemini-pro-latest", mods)

    def test_carril_pro_conserva_varios_modelos(self):
        with patch("proveedores_validador.esta_desactivado", return_value=False):
            mods = pc.obtener_modelos_tarea(self._prov(), "charla", carril="pro")
        self.assertIn("gemini-pro-latest", mods)
        self.assertGreaterEqual(len(mods), 2)


if __name__ == "__main__":
    unittest.main()
