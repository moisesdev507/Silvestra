"""Hotfix: streaming tolera callbacks en None (modo texto/silencio) sin fallback de error."""
import io
import unittest
from contextlib import ExitStack, redirect_stdout
from unittest.mock import patch

import proveedores_cadenas as pc
import respuesta_flujo

CRUDO = (
    "EMOCION: alegre\n"
    "RESPUESTA: Estoy bien, gracias por preguntar.\n"
    "ACCION: ninguna\n"
    "RECUERDO: ninguno"
)
RESPUESTA_ESPERADA = "Estoy bien, gracias por preguntar."


class _Cerebro:
    def __init__(self):
        self.historial = []
        self.turno_invitado = False
        self.memoria = None
        self.app = None

    def _podar_historial(self):
        pass

    def _obtener_historial_podado(self):
        return self.historial

    def instrucciones(self, texto):
        return "instrucciones de prueba"


def _proveedor(crudo=CRUDO, emitir=True, fallar=False):
    def completar(_mensajes, al_frase, **kwargs):
        if fallar:
            raise RuntimeError("fallo simulado de proveedor")
        if emitir:
            al_frase(RESPUESTA_ESPERADA)
        on_token = kwargs.get("on_primer_token")
        if callable(on_token):
            on_token()
        return crudo

    return completar


def _ejecutar(texto="¿Cómo estás?", al_frase=None, on_primer_token=None,
              proveedor=None, catalogo_operativo=False):
    cerebro = _Cerebro()
    parches = [
        patch("respuesta_flujo_acciones.atender", return_value=None),
        patch.object(respuesta_flujo.cerebro_enrutador, "verificar_pro_disponible",
                     return_value=False),
        patch.object(respuesta_flujo.cerebro_enrutador, "decidir_carril",
                     return_value=("rapido", "cotidiano_o_comando")),
        patch.object(respuesta_flujo.proveedores, "completar_flujo",
                     side_effect=proveedor or _proveedor()),
        patch.object(respuesta_flujo.pc, "clasificar_dificultad", return_value="charla"),
        patch("cerebro_historial.construir_ventana", return_value=[]),
        patch("aprendizaje.registrar_interaccion"),
        patch("cerebro_mentor.es_modo_mentor_activo", return_value=False),
    ]
    if catalogo_operativo:
        parches.append(patch("cerebro_prompt.describir_acciones_compactas",
                             return_value="ACCIONES: abrir_archivo"))
    with ExitStack() as pila:
        for parche in parches:
            pila.enter_context(parche)
        salida = io.StringIO()
        with redirect_stdout(salida):
            resultado = respuesta_flujo.responder_flujo(
                cerebro, texto, al_frase, on_primer_token=on_primer_token
            )
    return cerebro, resultado, salida.getvalue()


class TestStreamingCallbacksOpcionales(unittest.TestCase):
    def test_al_frase_none_no_rompe_streaming(self):
        """Reproduce el log: carril rápido, proveedor responde y al_frase=None."""
        cerebro, (resp, accion, _emo), salida = _ejecutar(
            al_frase=None, on_primer_token=None
        )
        self.assertEqual(resp, RESPUESTA_ESPERADA)
        self.assertIsNone(accion)
        self.assertNotIn(pc.FRASE_EMERGENCIA_LOCAL, resp)
        self.assertNotIn("Excepción en streaming", salida)
        self.assertNotIn("NoneType", salida)
        self.assertEqual(cerebro.historial[-1]["content"], resp)

    def test_al_frase_none_en_rama_diferida(self):
        """La emisión final de turnos operativos también tolera None."""
        _cerebro, (resp, _accion, _emo), salida = _ejecutar(
            texto="Abre eso", al_frase=None, catalogo_operativo=True
        )
        self.assertEqual(resp, RESPUESTA_ESPERADA)
        self.assertNotIn("Excepción en streaming", salida)
        self.assertNotIn("NoneType", salida)

    def test_callbacks_validos_siguen_recibiendo_fragmentos(self):
        emitidas = []
        tokens = []
        _cerebro, (resp, _accion, _emo), salida = _ejecutar(
            al_frase=emitidas.append, on_primer_token=lambda: tokens.append(1)
        )
        self.assertEqual(emitidas, [RESPUESTA_ESPERADA])
        self.assertEqual(tokens, [1])
        self.assertEqual(resp, RESPUESTA_ESPERADA)
        self.assertNotIn("Excepción en streaming", salida)

    def test_excepcion_real_loggea_traceback_y_mantiene_emergencia(self):
        _cerebro, (resp, _accion, _emo), salida = _ejecutar(
            al_frase=None, proveedor=_proveedor(fallar=True)
        )
        self.assertIn(pc.FRASE_EMERGENCIA_LOCAL, resp)
        self.assertIn("Excepción en streaming", salida)
        self.assertIn("[respuesta_flujo] traceback:", salida)
        self.assertIn("RuntimeError", salida)


if __name__ == "__main__":
    unittest.main()
