"""Regresión Hito 2: telemetría local instantánea y cierre limpio de voz."""
import queue
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import conversacion
import eventos
import respuesta_flujo
import telemetria

BAT = {"disponible": True, "porcentaje": 72, "cargando": False,
       "segundos_restantes": 3600}
SIS = {"cpu": 18, "ram_pct": 38, "ram_usada_gb": 6.2, "ram_total_gb": 16.0,
       "bateria": BAT, "texto": "CPU al 18%, RAM 6.2 de 16.0 GB (38%). Batería al 72%."}
DISCO = {"unidad": "C:\\", "libre_gb": 120.4, "total_gb": 475.0, "usado_pct": 75}
PROC = [("chrome", 820.5), ("code", 640.2), ("msedge", 310.0)]


@contextmanager
def datos_fijos():
    with patch.multiple(
        telemetria,
        estado_bateria=lambda: dict(BAT),
        estado_sistema=lambda: dict(SIS),
        estado_disco=lambda: dict(DISCO),
        procesos_pesados=lambda top=3: list(PROC)[:top],
    ):
        yield


class RelojFalso:
    def __init__(self):
        self.temporizadores = []

    def after(self, _ms, callback):
        self.temporizadores.append(callback)

    def drenar(self, tope=40):
        for _ in range(tope):
            if not self.temporizadores:
                return
            self.temporizadores.pop(0)()


class FlujoFalso:
    def __init__(self, voz, fin):
        self.voz, self.fin = voz, fin

    def agregar(self, frase, emocion=None):
        self.voz.frases.append(frase)
        self.voz.ocupada_estado = True
        self.voz.fin_pendiente = self.fin

    def cerrar(self):
        pass


class VozFalsa:
    def __init__(self):
        self.frases = []
        self.ocupada_estado = False
        self.fin_pendiente = None

    def ocupada(self):
        return self.ocupada_estado

    def flujo(self, fin=None, **_kw):
        return FlujoFalso(self, fin)

    def hablar(self, texto, fin=None, emocion=None):
        flujo = self.flujo(fin)
        flujo.agregar(texto)
        flujo.cerrar()

    def terminar(self):
        self.ocupada_estado = False
        fin, self.fin_pendiente = self.fin_pendiente, None
        if fin is not None:
            fin()


class CaraFalsa:
    def __init__(self, reloj):
        self.root = reloj
        self.escuchando = False
        self.burbujas = []

    def poner_escuchando(self, valor):
        self.escuchando = bool(valor)

    def decir(self, texto, _ms=None, emocion=None):
        self.burbujas.append(texto)

    def fijar_emocion(self, _emocion):
        pass

    def programar_retorno_neutral(self, _ms=None):
        pass


class TestTelemetriaLocal(unittest.TestCase):
    def setUp(self):
        p = patch.object(conversacion, "grabar", lambda app, generacion=None: None)
        p.start()
        self.addCleanup(p.stop)

    def test_consultas_devuelven_texto_conciso(self):
        casos = {
            "¿cuánta batería me queda?": ("Batería al 72%", "60 minutos"),
            "cómo está la batería": ("Batería al 72%",),
            "qué porcentaje de batería tengo": ("Batería al 72%",),
            "¿cómo va la laptop?": ("CPU al 18%", "RAM 6.2 de 16.0 GB"),
            "estado del sistema": ("CPU al 18%",),
            "cuánta RAM estoy usando": ("RAM 6.2 de 16.0 GB",),
            "cómo está la CPU": ("CPU al 18%",),
            "¿cuánto espacio libre tengo en el disco?": ("120 GB libres", "75% ocupado"),
            "cómo está el almacenamiento": ("GB libres",),
            "¿qué me está consumiendo tanta memoria?": ("chrome (820.5 MB)",),
            "qué programa me está trabando la PC": ("code (640.2 MB)",),
            "qué usa más CPU": ("msedge (310.0 MB)",),
        }
        with datos_fijos():
            for texto, esperados in casos.items():
                resp = telemetria.responder_telemetria(texto)
                self.assertIsInstance(resp, str, texto)
                self.assertLessEqual(len(resp), 160, texto)
                for esperado in esperados:
                    self.assertIn(esperado, resp)

    def test_preguntas_conceptuales_no_se_interceptan(self):
        with datos_fijos():
            for texto in (
                "¿qué es la memoria RAM?", "¿qué es la CPU?", "¿qué es la batería?",
                "¿cómo funciona una batería de litio?", "explícame qué es una CPU",
                "¿para qué sirve el disco duro?", "hola, ¿cómo estás?",
            ):
                self.assertIsNone(telemetria.responder_telemetria(texto), texto)

    def test_sensors_battery_none_es_seguro(self):
        falso = SimpleNamespace(sensors_battery=lambda: None,
                                POWER_TIME_UNLIMITED=-1, POWER_TIME_UNKNOWN=-2)
        sin_bat = (12, 40, {"disponible": False, "porcentaje": 0,
                            "cargando": False})
        with patch.object(telemetria, "psutil", falso), \
             patch("pantalla_remota_datos.obtener_telemetria_hardware",
                   return_value=sin_bat):
            b = telemetria.estado_bateria()
            self.assertFalse(b["disponible"])
            self.assertIsNone(b["segundos_restantes"])
            with patch.object(telemetria, "estado_bateria", lambda: b):
                resp = telemetria.responder_telemetria("¿cuánta batería me queda?")
            self.assertIn("No detecto batería", resp)

    def _app(self):
        reloj = RelojFalso()
        voz = VozFalsa()
        cara = CaraFalsa(reloj)
        app = SimpleNamespace(
            cola=queue.Queue(), conversacion=True, escuchando=False, flujo=None,
            texto_flujo="", _flujo_cerrado=False, voz=voz, cara=cara,
            musica_activa=False, pendiente_descanso=False, escenario=None,
            _t_accion_llm=0, ultimo_dicho="", silencios=0, _ecosistema_origen=None,
            t_fin_habla=None, metricas_turno=None, t_inicio_texto=None,
        )
        app.escuchar = lambda: conversacion.escuchar(app)
        app._dejar_de_escuchar = lambda: conversacion.dejar_de_escuchar(app)
        app._es_eco = lambda _texto: False
        app.decir = lambda texto, **kw: voz.hablar(
            texto, lambda: app.cola.put(("fin_voz", None)), emocion=kw.get("emocion"))
        app.ejecutar = lambda _linea: self.fail("No se debe ejecutar ninguna acción")
        return app, reloj, voz, cara

    def _drenar(self, app):
        while not app.cola.empty():
            tipo, valor = app.cola.get_nowait()
            eventos.atender_evento(app, tipo, valor)

    def test_flujo_real_una_voz_y_aro_amarillo(self):
        app, reloj, voz, cara = self._app()
        cerebro = SimpleNamespace(historial=[], app=app)
        with datos_fijos(), \
             patch.object(respuesta_flujo.proveedores, "completar_flujo",
                          side_effect=AssertionError("Se llamó al LLM")), \
             patch.object(respuesta_flujo.cerebro_enrutador, "completar_pro_flujo",
                          side_effect=AssertionError("Se llamó al LLM")):
            resultado = respuesta_flujo.responder_flujo(
                cerebro, "Lyris, ¿cuánta batería me queda?",
                lambda frase: app.cola.put(("frase", frase)))
            self.assertEqual(resultado[0], "Batería al 72%, descargando. Te quedan unos 60 minutos.")
            self.assertIsNone(resultado[1])
            app.cola.put(("respuesta", resultado))
            self._drenar(app)

        self.assertEqual(voz.frases, [resultado[0]])
        self.assertTrue(voz.ocupada())
        voz.terminar()
        self._drenar(app)
        reloj.drenar()

        self.assertFalse(voz.ocupada())
        self.assertIsNone(app.flujo)
        self.assertTrue(app.escuchando)
        self.assertTrue(cara.escuchando)


if __name__ == "__main__":
    unittest.main()
