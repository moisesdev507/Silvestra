"""Hotfix: intención operativa, errata 'minimaliza' y verdad antes de hablar."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import acciones
import cerebro_prompt_compacto as cpc
import respuesta_flujo
import respuesta_flujo_acciones as rfa


OFERTA_MUSICA = (
    "A mí me interesa más el mix de música que tienes en el centro, el de "
    "«Soft Lofi» o cualquier opción relajante para ambientar mientras trabajamos. "
    "¿Te pongo algo de eso?"
)
HISTORIAL_OFRECIMIENTO = [
    {"role": "user", "content": "Mira la pantalla y dime cual te interesa más"},
    {"role": "assistant", "content": OFERTA_MUSICA},
]


def _registrar_stubs():
    """El registro VIVAS real se crea al importar control_laptop en la app."""
    if "minimizar_todo" not in acciones.VIVAS:
        acciones.registrar("minimizar_todo", lambda: (True, "Listo."), "minimiza todas las ventanas")
    for nombre in ("musica_youtube", "poner_musica"):
        if nombre not in acciones.VIVAS:
            acciones.registrar(
                nombre, lambda arg: (True, "Listo."), "reproduce música en YouTube",
                con_texto=True,
            )


_registrar_stubs()


class _Cerebro:
    def __init__(self, historial=None):
        self.historial = list(historial or [])
        self.turno_invitado = False
        self.memoria = None
        self.app = None

    def _podar_historial(self):
        pass

    def _obtener_historial_podado(self):
        return self.historial

    def instrucciones(self, texto):
        return "instrucciones de prueba"


class TestIntencionOperativa(unittest.TestCase):
    def test_afirmacion_tras_oferta_activa_catalogo_de_musica(self):
        catalogo = cpc.catalogo_condicional(
            "Sí, ponme algo de eso.", acciones, historial_reciente=HISTORIAL_OFRECIMIENTO
        )
        self.assertNotEqual(catalogo, cpc.BLOQUE_MINIMO)
        self.assertIn("musica_youtube", catalogo)
        self.assertIn("poner_musica", catalogo)
        self.assertTrue(cpc.tiene_intencion_operativa("dale, hazlo", HISTORIAL_OFRECIMIENTO))
        self.assertEqual(cpc.catalogo_condicional("vale, perfecto", acciones), cpc.BLOQUE_MINIMO)

    def test_errata_minimaliza_activa_catalogo_y_se_intercepta(self):
        catalogo = cpc.catalogo_condicional("Lyris, Minimaliza la ventana", acciones)
        self.assertIn("minimizar_todo", catalogo)
        self.assertTrue(rfa.es_minimizar("Lyris, Minimaliza la ventana"))
        self.assertTrue(rfa.es_minimizar("minimiza la ventana"))
        self.assertFalse(rfa.es_minimizar("no minimices la ventana"))

        cerebro = _Cerebro()
        emitidas = []
        resultado = rfa.atender(
            cerebro, "Lyris, Minimaliza la ventana", "Lyris, Minimaliza la ventana",
            emitidas.append,
        )
        self.assertEqual(resultado, ("Minimizando la ventana.", "minimizar_todo", "alegre"))
        self.assertEqual(emitidas, ["Minimizando la ventana."])
        self.assertEqual([m["role"] for m in cerebro.historial], ["user", "assistant"])

    def test_guard_corrgimiento_no_miente(self):
        texto = "Lyris, Minimaliza la ventana"
        respuesta, accion, cambio = rfa.sanear_intencion_operativa(
            texto, "Ya minimicé la ventana de YouTube.", None
        )
        self.assertTrue(cambio)
        self.assertEqual(accion, "minimizar_todo")
        self.assertEqual(respuesta, "Listo, lo hago.")

        respuesta, accion, cambio = rfa.sanear_intencion_operativa(
            "Sí, ponme algo de eso.", "Ya te puse un mix de lofi.", None,
            historial=HISTORIAL_OFRECIMIENTO,
        )
        self.assertTrue(cambio)
        self.assertTrue(str(accion).startswith("musica_youtube"))
        self.assertNotIn("ya te puse", respuesta.lower())

        respuesta, accion, cambio = rfa.sanear_intencion_operativa(
            "Hola, ¿cómo estás?", "Estoy bien, gracias.", None
        )
        self.assertFalse(cambio)
        self.assertIsNone(accion)

    def test_streaming_no_sintetiza_promesa_sin_accion(self):
        cerebro = _Cerebro(HISTORIAL_OFRECIMIENTO)
        emitidas = []

        def completar(_mensajes, al_frase, **_kwargs):
            al_frase("¡Listo!")
            al_frase("Ya te puse un mix de lofi suave para acompañarte.")
            return (
                "EMOCION: alegre\n"
                "RESPUESTA: ¡Listo! Ya te puse un mix de lofi suave para acompañarte.\n"
                "ACCION: ninguna\n"
                "RECUERDO: ninguno"
            )

        with patch.object(rfa, "atender", return_value=None), \
             patch.object(respuesta_flujo.cerebro_enrutador, "verificar_pro_disponible", return_value=False), \
             patch.object(respuesta_flujo.cerebro_enrutador, "decidir_carril",
                          return_value=("rapido", "cotidiano_o_comando")), \
             patch.object(respuesta_flujo.proveedores, "completar_flujo", side_effect=completar), \
             patch.object(respuesta_flujo.pc, "clasificar_dificultad", return_value="charla"), \
             patch("cerebro_historial.construir_ventana", return_value=[]), \
             patch("aprendizaje.registrar_interaccion"), \
             patch("cerebro_mentor.es_modo_mentor_activo", return_value=False):
            respuesta, accion, _emo = respuesta_flujo.responder_flujo(
                cerebro, "Sí, ponme algo de eso.", emitidas.append
            )

        self.assertEqual(emitidas, ["Listo, lo hago."])
        self.assertNotIn("ya te puse", respuesta.lower())
        self.assertTrue(str(accion).startswith("musica_youtube"))
        self.assertEqual(cerebro.historial[-1]["content"], respuesta)


if __name__ == "__main__":
    unittest.main()
