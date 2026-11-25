"""Pruebas unitarias para iniciativa_kaya: temas abiertos, resumen compacto y reglas anti-fastidio."""
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import iniciativa_kaya
import vigilante_proactivo as vig


class TestIniciativaKaya(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.tmp.close()
        iniciativa_kaya.RUTA_TEMAS = self.tmp.name
        iniciativa_kaya._cache_temas = []
        iniciativa_kaya._ultimo_disparo_iniciativa = 0.0

    def tearDown(self):
        try:
            if os.path.exists(self.tmp.name):
                os.remove(self.tmp.name)
        except Exception:
            pass

    def test_creacion_limite_y_cierre_de_temas(self):
        """Verifica que se registren temas, se respete el límite de 5 y se cierren al resolverse."""
        # Registrar 6 temas para probar límite de 5
        for i in range(1, 7):
            ok = iniciativa_kaya.registrar_tema_abierto(f"Proyecto {i}", contexto=f"Trabajando en {i}")
            self.assertTrue(ok)
            time.sleep(0.01)

        temas = iniciativa_kaya.obtener_temas_abiertos()
        self.assertLessEqual(len(temas), 5)
        nombres = [t["tema"] for t in temas]
        self.assertIn("Proyecto 6", nombres)
        self.assertNotIn("Proyecto 1", nombres)  # El más antiguo fue podado

        # Cerrar un tema
        cerrado = iniciativa_kaya.cerrar_tema("Ya terminé lo de Proyecto 6 por fin")
        self.assertTrue(cerrado)
        temas_tras_cierre = iniciativa_kaya.obtener_temas_abiertos()
        nombres_tras_cierre = [t["tema"] for t in temas_tras_cierre]
        self.assertNotIn("Proyecto 6", nombres_tras_cierre)

    def test_resumen_compacto_en_ram(self):
        """Verifica que resumen_compacto_temas devuelva una frase ultraligera < 200 caracteres."""
        iniciativa_kaya.registrar_tema_abierto("Entrega de Programación I", contexto="Preparando parcial")
        resumen = iniciativa_kaya.resumen_compacto_temas()
        self.assertTrue(resumen.startswith("Tema abierto pendiente:"))
        self.assertIn("Programación I", resumen)
        self.assertLess(len(resumen), 180)

    def test_respeto_estricto_cooldown_y_usuario_ocupado(self):
        """Verifica que evaluar_iniciativa_organica respete cooldown y no moleste si el usuario está ocupado."""
        ahora = 10000.0
        # Configurar tema creado hace más de 4 horas
        iniciativa_kaya._cache_temas = [{
            "tema": "Propuesta web negocio local",
            "contexto": "Avanzando diseño",
            "creado_en": ahora - 5 * 3600,
            "ultimo_seguimiento": ahora - 5 * 3600,
            "estado": "abierto"
        }]

        app_libre = SimpleNamespace(
            escuchando=False,
            voz=SimpleNamespace(ocupada=lambda: False),
            musica_activa=False,
            sistema_multimodal=None
        )

        # 1. Con usuario libre y cooldown vencido -> Genera intervención orgánica cálida
        intervencion = iniciativa_kaya.evaluar_iniciativa_organica(app_libre, ahora=ahora)
        self.assertIsNotNone(intervencion)
        self.assertIn("Propuesta web", intervencion["mensaje"])
        self.assertIn("¿cómo te fue", intervencion["mensaje"].lower())

        # 2. Inmediatamente después -> Bloqueado por cooldown (45 min)
        intervencion_pronta = iniciativa_kaya.evaluar_iniciativa_organica(app_libre, ahora=ahora + 300.0)
        self.assertIsNone(intervencion_pronta)

        # 3. Tras 50 min pero con usuario ocupado (reproduciendo música o hablando) -> Bloqueado
        app_ocupado = SimpleNamespace(
            escuchando=True,
            voz=SimpleNamespace(ocupada=lambda: True),
            musica_activa=True,
            sistema_multimodal=None
        )
        intervencion_ocupado = iniciativa_kaya.evaluar_iniciativa_organica(app_ocupado, ahora=ahora + 50 * 60)
        self.assertIsNone(intervencion_ocupado)


if __name__ == "__main__":
    unittest.main()
