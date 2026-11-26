"""Hilo conversacional continuo (Live/Celeste) y retorno automático a Reposo Azul."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cara_orbe_hibrido as coh
import cerebro_hilo
import live_turno
import memoria_contexto
import respuesta_flujo

RAIZ = os.path.dirname(os.path.abspath(__file__))


def _limpiar_turnos():
    memoria_contexto.instalar_espejo(None)
    with memoria_contexto._bloqueo:
        memoria_contexto._TURNOS.clear()


class TestAcumulacionLive(unittest.TestCase):
    def setUp(self):
        _limpiar_turnos()

    def tearDown(self):
        _limpiar_turnos()

    def test_fragmentos_parciales_se_guardan_completos(self):
        ac = live_turno.AcumuladorTurnos()
        for parte in ("Hola,", "Hola, ¿cómo", "Hola, ¿cómo estás?"):
            ac.agregar_usuario(parte)
        for parte in ("Estoy", "Estoy bien,", "Estoy bien, ¿y tú?"):
            ac.agregar_kaya(parte)
        self.assertTrue(ac.vaciar())
        self.assertEqual(memoria_contexto.historial_conversacion_activa()[-2:], [
            {"role": "user", "content": "Hola, ¿cómo estás?"},
            {"role": "assistant", "content": "Estoy bien, ¿y tú?"},
        ])
        self.assertFalse(ac.vaciar())

    def test_cfg_se_reconstruye_con_el_hilo_reciente(self):
        memoria_contexto.registrar_turno("user", "Hablemos de Supabase")
        memoria_contexto.registrar_turno("kaya", "Claro, ¿qué parte?")
        with patch("live_turno.live_herramientas.declarar_declaraciones_herramientas",
                   return_value=[]):
            cfg1 = live_turno.construir_config("Kaya", False, False, "Moisés")
            cfg2 = live_turno.construir_config("Kaya", False, False, "Moisés")
        uno = cfg1.system_instruction.parts[0].text
        dos = cfg2.system_instruction.parts[0].text
        for texto in (uno, dos):
            self.assertIn("[Conversación reciente en curso]", texto)
            self.assertIn("Hablemos de Supabase", texto)
            self.assertIn("¿qué parte?", texto)
        self.assertEqual(uno, dos)


class TestHiloCompartido(unittest.TestCase):
    def setUp(self):
        _limpiar_turnos()

    def tearDown(self):
        _limpiar_turnos()

    def test_espejo_y_cambio_live_celeste_conservan_el_hilo(self):
        cerebro = SimpleNamespace(historial=[], _podar_historial=lambda: None)
        memoria_contexto.instalar_espejo(
            lambda rol, texto: cerebro_hilo.reflejar_turno(cerebro.historial, rol, texto)
        )
        memoria_contexto.registrar_turno("user", "Sobre eso de Supabase")
        memoria_contexto.registrar_turno("kaya", "Sí, la consulta lenta.")
        self.assertEqual(cerebro.historial[-2:], [
            {"role": "user", "content": "Sobre eso de Supabase"},
            {"role": "assistant", "content": "Sí, la consulta lenta"},
        ])

        respuesta_flujo._reg_turno(cerebro, "Sígueme contando", "El índice faltaba.")
        historial = memoria_contexto.historial_conversacion_activa()
        contenidos = [h["content"] for h in historial]
        self.assertIn("Sígueme contando", contenidos)
        self.assertIn("El índice faltaba", contenidos)

        mensajes = cerebro_hilo.historial_podado(cerebro.historial)
        self.assertIn("Conversación reciente en curso", mensajes[0]["content"])
        self.assertTrue(any("índice faltaba" in h["content"] for h in mensajes))

    def test_ventana_respeta_doce_turnos_y_mil_cuatrocientos_caracteres(self):
        for i in range(20):
            memoria_contexto.registrar_turno(
                "user" if i % 2 == 0 else "kaya", f"Turno {i} " + ("x" * 80)
            )
        historial = memoria_contexto.historial_conversacion_activa()
        self.assertLessEqual(len(historial), 12)
        self.assertLessEqual(sum(len(h["content"]) for h in historial), 1400)
        self.assertIn("Turno 19", historial[-1]["content"])


class TestReposoAzul(unittest.TestCase):
    def test_umbral_silencio_y_envio_de_estado(self):
        with open(os.path.join(RAIZ, "live_webrtc.py"), encoding="utf-8") as f:
            fuente = f.read()
        self.assertRegex(
            fuente, r"uActivo\s*=\s*Math\.max\(0\.0065\s*,\s*piso\s*\*\s*1\.65\)"
        )
        self.assertIn("ahora-ultimoHabla>9000", fuente)
        self.assertIn("dormida=true", fuente)
        self.assertIn('sendCtrl({type:"estado",v:"reposo"})', fuente)
        self.assertIn("if(!dormida){ws.send", fuente)
        self.assertIn("if(framesVoz>=2)ultimoHabla=ahora", fuente)

        # Ruido sostenido por debajo del umbral: el reloj de 9 s avanza solo.
        piso = min(0.007, 0.012 * 0.98 + 0.008 * 0.02)
        umbral = max(0.0065, piso * 1.65)
        self.assertGreater(umbral, 0.008)
        ultimo_habla, ahora, dormida = 0.0, 0.0, False
        for _ in range(91):
            ahora += 100.0
            rms = 0.008
            if rms > umbral:
                ultimo_habla = ahora
            if not dormida and ahora - ultimo_habla > 9000:
                dormida = True
        self.assertTrue(dormida)

        # Habla real por encima del umbral reinicia el reloj y mantiene Live abierto.
        for _ in range(2):
            ahora += 50.0
            if 0.02 > umbral:
                ultimo_habla = ahora
        self.assertEqual(ultimo_habla, ahora)

    def test_orbe_interpola_hacia_azul_profundo_con_micro_cerrado(self):
        cara = SimpleNamespace(
            voz_silenciada=False, baile_hasta=0.0, hablando=True, escuchando=True,
            pensando=False, pensando_hasta=0.0, nivel_volumen=0.0,
            micro_live_cerrado=True, estado_live="reposo",
        )
        orbe = coh.GestorOrbeHibrido()
        self.assertEqual(orbe.deducir_estado(cara), "reposo")
        for i in range(80):
            orbe.actualizar(cara, t=float(i) * 0.016, nivel_rms=0.0)
        paleta = coh.PALETAS["reposo"]
        self.assertEqual(set(paleta), {
            "centro", "medio", "borde", "halo", "acento",
            "plasma1", "plasma2", "plasma3",
        })
        self.assertEqual(paleta["medio"].name(), "#1d4ed8")
        self.assertEqual(paleta["plasma2"].name(), "#3b82f6")
        self.assertLess(
            abs(orbe._colores_suaves["medio"].blue() - paleta["medio"].blue()), 6
        )
        self.assertLess(
            abs(orbe._colores_suaves["plasma2"].green() - paleta["plasma2"].green()), 6
        )
        cara.micro_live_cerrado = False
        cara.hablando = cara.escuchando = False
        self.assertEqual(orbe.deducir_estado(cara), "reposo")


if __name__ == "__main__":
    unittest.main(verbosity=2)
