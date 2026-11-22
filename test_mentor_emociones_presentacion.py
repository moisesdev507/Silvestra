"""Pruebas unitarias para Modo Mentora, Presentación Dinámica y Expresiones Faciales/Vocales."""
import os
import unittest
from unittest.mock import MagicMock


class TestCaraEmociones(unittest.TestCase):
    """Verifica perfiles faciales y prosodia vocal de emociones nuevas y dinámicas."""

    def test_obtener_rasgos_nuevas_emociones(self):
        import cara_emociones
        for emo in ("concentrada", "firme", "enojada", "orgullosa", "neutral"):
            rasgos = cara_emociones.obtener_rasgos(emo)
            self.assertEqual(len(rasgos), 7, f"Rasgos incompletos para {emo}")
            # cejas_y, cejas_ang, ojos_ap, boca_curva, boca_ancho, rubor, color
            self.assertIsInstance(rasgos[0], float)
            self.assertIsInstance(rasgos[1], float)
            self.assertIsInstance(rasgos[2], float)

    def test_normalizacion_alias_emociones(self):
        import cara_emociones
        # 'concentrado' -> 'concentrada'
        rasgos_m = cara_emociones.obtener_rasgos("concentrado")
        rasgos_f = cara_emociones.obtener_rasgos("concentrada")
        self.assertEqual(rasgos_m, rasgos_f)

        # 'enojado' / 'molesta' -> 'firme'
        rasgos_enojado = cara_emociones.obtener_rasgos("enojado")
        rasgos_firme = cara_emociones.obtener_rasgos("firme")
        self.assertEqual(rasgos_enojado, rasgos_firme)

    def test_prosodia_vocal(self):
        import cara_emociones
        pros = cara_emociones.obtener_prosodia("orgullosa")
        self.assertIn("rate", pros)
        self.assertIn("pitch", pros)
        self.assertIn("volume", pros)

    def test_enriquecimiento_voz_sin_modificar_archivo(self):
        import cara_emociones
        import voz
        for k in ("concentrada", "firme", "orgullosa"):
            self.assertIn(k, voz.EMOCIONES_VOZ)


class TestCerebroMentor(unittest.TestCase):
    """Verifica el GestorMentor, directiva socrática y consolidación cognitiva."""

    def setUp(self):
        import cerebro_mentor
        self.gestor = cerebro_mentor.GestorMentor()

    def test_activacion_y_desactivacion(self):
        self.assertFalse(self.gestor.esta_activo())
        self.assertEqual(self.gestor.obtener_directiva_prompt(), "")

        msg_act = self.gestor.activar()
        self.assertTrue(self.gestor.esta_activo())
        self.assertIn("activado", msg_act.lower())

        directiva = self.gestor.obtener_directiva_prompt()
        self.assertIn("MODO MENTORA", directiva)
        self.assertLessEqual(len(directiva), 220, "La directiva debe medir <= 220 caracteres")

        msg_des = self.gestor.desactivar()
        self.assertFalse(self.gestor.esta_activo())
        self.assertEqual(self.gestor.obtener_directiva_prompt(), "")
        self.assertIn("desactivado", msg_des.lower())

    def test_deteccion_ordenes_mentora(self):
        import cerebro_mentor
        # Activación
        r_act = cerebro_mentor.detectar_orden_mentora("Lyris, activa el modo mentora por favor")
        self.assertIsNotNone(r_act)
        self.assertEqual(r_act[0], "activar")
        self.assertEqual(r_act[2], "concentrada")

        # Modo programación
        r_prog = cerebro_mentor.detectar_orden_mentora("entra en modo programacion")
        self.assertIsNotNone(r_prog)
        self.assertEqual(r_prog[0], "activar")

        # Desactivación
        r_des = cerebro_mentor.detectar_orden_mentora("desactiva el modo mentora")
        self.assertIsNotNone(r_des)
        self.assertEqual(r_des[0], "desactivar")
        self.assertEqual(r_des[2], "calida")

        # Consolidación
        r_con = cerebro_mentor.detectar_orden_mentora("consolida lo aprendido en la sesion")
        self.assertIsNotNone(r_con)
        self.assertEqual(r_con[0], "consolidar")
        self.assertEqual(r_con[2], "orgullosa")

    def test_consolidacion_aprendizaje_en_grafo(self):
        import cerebro_mentor
        import cerebro_trabajo
        cerebro_trabajo.actualizar_archivo("workspace_lyris/test_arquitectura.py")
        cerebro_trabajo.actualizar_habilidad("auditar_seguridad")

        res = cerebro_mentor.consolidar_aprendizaje(creador="Moisés")
        self.assertIn("grafo de conocimiento", res)


class TestPresentacionDinamica(unittest.TestCase):
    """Verifica la presentación profesional con métricas en vivo."""

    def test_detectar_orden_presentacion(self):
        import presentacion
        self.assertTrue(presentacion.detectar_orden_presentacion("Lyris, presentate por favor"))
        self.assertTrue(presentacion.detectar_orden_presentacion("quien eres tu"))
        self.assertTrue(presentacion.detectar_orden_presentacion("que puedes hacer"))
        self.assertFalse(presentacion.detectar_orden_presentacion("enciende la luz"))

    def test_generar_presentacion_dinamica(self):
        import presentacion
        mock_app = MagicMock()
        mock_app.memoria.nombre = "Lyris"
        mock_app.memoria.creador = "Moisés"

        texto, emo = presentacion.generar_presentacion_dinamica(mock_app)
        self.assertIn("Lyris", texto)
        self.assertIn("Moisés", texto)
        self.assertEqual(emo, "orgullosa")


class TestIntegracionPromptYFlujo(unittest.TestCase):
    """Verifica la inyección en el prompt y respuesta_flujo."""

    def test_directiva_mentor_en_prompt(self):
        import cerebro_mentor
        import cerebro_prompt
        cerebro_mentor.activar_mentor()
        try:
            mock_mem = MagicMock()
            mock_mem.hechos = []
            mock_mem.creador = "Moisés"
            p = cerebro_prompt.construir_prompt(mock_mem, texto_actual="cómo refactorizo esto?")
            self.assertIn("MODO MENTORA", p)
        finally:
            cerebro_mentor.desactivar_mentor()

    def test_intercepcion_mentora_en_respuesta_flujo(self):
        import respuesta_flujo
        mock_cerebro = MagicMock()
        mock_cerebro.historial = []
        resp, accion, emo = respuesta_flujo.responder_flujo(mock_cerebro, "activa modo mentora", al_frase=None)
        self.assertIn("Modo mentora socrática activado", resp)
        self.assertIsNone(accion)
        self.assertEqual(emo, "concentrada")

    def test_intercepcion_presentacion_en_respuesta_flujo(self):
        import respuesta_flujo
        mock_cerebro = MagicMock()
        mock_cerebro.historial = []
        resp, accion, emo = respuesta_flujo.responder_flujo(mock_cerebro, "preséntate", al_frase=None)
        self.assertIn("asistente", resp.lower())
        self.assertIsNone(accion)
        self.assertEqual(emo, "orgullosa")


if __name__ == "__main__":
    unittest.main()
