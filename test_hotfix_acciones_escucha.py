"""Hotfix: una sola voz por acción de sistema y escucha siempre rearmada."""
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import eventos
import eventos_dialogo
import oido as modulo_oido


class _Raiz:
    """Raiz Qt falsa: guarda temporizadores y permite ejecutarlos a voluntad."""

    def __init__(self):
        self.temporizadores = []
        self.cancelados = []

    def after(self, ms, fn):
        self.temporizadores.append((ms, fn))
        return len(self.temporizadores) - 1

    def after_cancel(self, identificador):
        self.cancelados.append(identificador)

    def ejecutar_todos(self, max_vueltas=20):
        for _ in range(max_vueltas):
            if not self.temporizadores:
                return
            pendientes, self.temporizadores = self.temporizadores, []
            for _ms, fn in pendientes:
                fn()


class _FlujoVoz:
    def __init__(self, voz):
        self.voz = voz
        self.frases = []
        self.cerrado = False

    def agregar(self, frase, emocion=None):
        self.frases.append(frase)

    def cerrar(self):
        self.cerrado = True
        self.voz.activos = 0
        self.voz.cola.append(("fin_voz", None))


class _Voz:
    def __init__(self, cola):
        self.cola = cola
        self.activos = 0
        self.flujos = []
        self.cancelaciones = 0

    def flujo(self, al_terminar=None, emocion="neutral", **kwargs):
        flujo = _FlujoVoz(self)
        self.flujos.append(flujo)
        self.activos = 1
        return flujo

    def ocupada(self):
        return self.activos > 0

    def cancelar(self, motivo="prueba"):
        self.cancelaciones += 1
        self.activos = 0


class _Cara:
    def __init__(self, root):
        self.root = root
        self.burbujas = []
        self.escuchando_visual = None

    def fijar_emocion(self, emocion):
        pass

    def decir(self, texto, ms=None, emocion=None):
        self.burbujas.append(texto)

    def poner_escuchando(self, activo):
        self.escuchando_visual = activo

    def actualizar_subtitulo(self, texto):
        pass

    def programar_retorno_neutral(self, ms):
        pass

    def isVisible(self):
        return False


class _App:
    def __init__(self, conversacion=True):
        self.cola = []
        self.voz = _Voz(self.cola)
        self.cara = _Cara(_Raiz())
        self.conversacion = conversacion
        self.escuchando = False
        self.flujo = None
        self.texto_flujo = ""
        self._frases_flujo_emitidas = 0
        self.ultimo_dicho = ""
        self.origen_entrada_actual = "microfono"
        self._ecosistema_origen = None
        self.musica_activa = False
        self.pendiente_descanso = False
        self.descansando = False
        self.ejecuciones = []
        self.rearmados = 0
        self.asegurar_llamadas = 0
        self._generacion_escucha = 0
        self._t_accion_llm = 0.0
        self._ultima_accion_sistema = ""
        self._reanudar_intentos = 0
        self.oido = SimpleNamespace(asegurar_flujo=self._asegurar_flujo)

    def _asegurar_flujo(self):
        self.asegurar_llamadas += 1

    def ejecutar(self, linea):
        self.ejecuciones.append(linea)
        if "minimizar" in str(linea):
            self.cola.append(("frase", "Minimizando todas las ventanas."))
        elif "bloquear" in str(linea):
            self.cola.append(("frase", "Pantalla bloqueada."))

    def _dejar_de_escuchar(self):
        self._generacion_escucha += 1
        self.escuchando = False
        self.cara.poner_escuchando(False)

    def escuchar(self):
        if self.escuchando or not self.conversacion:
            return
        self._generacion_escucha += 1
        self.escuchando = True
        self.cara.poner_escuchando(True)
        self.oido.asegurar_flujo()
        self.rearmados += 1


def _drenar_cola(app):
    while app.cola:
        tipo, texto = app.cola.pop(0)
        eventos.atender_evento(app, tipo, texto)


class TestAccionUnicaYVoz(unittest.TestCase):
    def test_minimizar_ventana_actual_no_encadena_segunda_accion_ni_voz(self):
        app = _App()
        app.flujo = app.voz.flujo()
        app.flujo.agregar("¡Claro!")
        app.flujo.agregar("Minimizando la ventana de Edge.")
        app._frases_flujo_emitidas = 2

        eventos.atender_evento(
            app,
            "respuesta",
            ("¡Claro! Minimizando la ventana de Edge.", "minimizar_todo", "alegre"),
        )
        _drenar_cola(app)

        self.assertEqual(app.ejecuciones, ["minimizar_todo"])
        self.assertEqual(len(app.voz.flujos), 1)
        self.assertNotIn("Minimizando todas las ventanas.", app.voz.flujos[0].frases)
        self.assertFalse(any("Minimizando todas las ventanas." in b for b in app.cara.burbujas))
        self.assertTrue(any(ms == 700 for ms, _fn in app.cara.root.temporizadores))

        app.cara.root.ejecutar_todos()
        self.assertTrue(app.escuchando)
        self.assertEqual(app.asegurar_llamadas, 1)

    def test_bloquear_rearma_escucha_y_suspender_no_la_rearma(self):
        app = _App()
        eventos_dialogo.reanudar_escucha(app, "bloquear_pantalla")
        app.cara.root.ejecutar_todos()
        self.assertTrue(app.escuchando)
        self.assertEqual(app.asegurar_llamadas, 1)

        silence = _App()
        eventos_dialogo.reanudar_escucha(silence, "suspender_laptop")
        silence.cara.root.ejecutar_todos()
        self.assertFalse(silence.escuchando)
        self.assertEqual(silence.asegurar_llamadas, 0)

    def test_frase_huerfana_cierra_flujo_y_rearma_escucha(self):
        app = _App()
        eventos.atender_evento(app, "frase", "Aviso autónomo importante.")
        flujo = app.flujo
        self.assertIsNotNone(flujo)

        app.cara.root.ejecutar_todos()
        _drenar_cola(app)
        app.cara.root.ejecutar_todos()

        self.assertTrue(flujo.cerrado)
        self.assertIsNone(app.flujo)
        self.assertTrue(app.escuchando)
        self.assertEqual(app.asegurar_llamadas, 1)


class TestOidoSinBloqueo(unittest.TestCase):
    def test_espera_antieco_no_cuelga_si_la_voz_queda_ocupada(self):
        oido = object.__new__(modulo_oido.Oido)
        dormidos = []
        lecturas = []

        flujo = SimpleNamespace(
            asegurar_flujo=lambda: None,
            drenar=lambda: None,
            aplicar_guarda_antieco=lambda **kwargs: None,
            leer=lambda timeout: lecturas.append(timeout) or None,
        )
        vad = SimpleNamespace(
            reset=lambda: None,
            flush=lambda: None,
            hay_segmento_completo=lambda: False,
        )
        app = SimpleNamespace(
            voz=SimpleNamespace(ocupada=lambda: True),
            escuchando=True,
            conversacion=True,
        )
        oido._flujo = flujo
        oido._vad = vad
        oido._sesion_vigente = lambda aplicación, generación: True

        with patch.object(modulo_oido.time, "monotonic", side_effect=[0.0, 0.0, 3.0]), \
             patch.object(modulo_oido.time, "time", side_effect=[0.0, 10.0, 10.0]), \
             patch.object(modulo_oido.time, "sleep", side_effect=dormidos.append):
            resultado = oido._escuchar(app=app, generacion=1)

        self.assertIsNone(resultado)
        self.assertEqual(len(dormidos), 1)
        self.assertEqual(lecturas, [0.08])


if __name__ == "__main__":
    unittest.main()
