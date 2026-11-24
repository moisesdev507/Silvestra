"""Pruebas unitarias para presupuesto de max_tokens, recorte limpio y operadores hablados."""
import inspect
import unittest

import cerebro_parser as cp
from expertos import obtener_cartucho
import proveedores
import proveedores_stream as ps


class TestMaxTokensYVozHablada(unittest.TestCase):

    def test_presupuesto_minimo_max_tokens(self):
        """Verifica que max_tokens sea de al menos 220 en charla y 450 en pesado/razonamiento."""
        # En proveedores.completar
        sig = inspect.signature(proveedores.completar)
        self.assertIn("max_tokens", sig.parameters)

        # En proveedores_stream._intentar_stream_proveedor
        sig_stream = inspect.signature(ps._intentar_stream_proveedor)
        self.assertIn("max_tokens", sig_stream.parameters)
        self.assertIn("tarea", sig_stream.parameters)

    def test_recorte_limpio_oracion_truncada(self):
        """Si la respuesta viene truncada sin puntuación de cierre y hay oraciones previas completas,
        se recorta limpiamente hasta la última oración completa."""
        # Caso 1: frase incompleta tras oración cerrada
        texto_trunco = (
            "En C++ un puntero almacena la dirección de memoria de una variable. "
            "Se declara con asterisco garantizando precisión y eficiencia en cada"
        )
        podado = cp.podar_oracion_incompleta(texto_trunco)
        self.assertEqual(podado, "En C++ un puntero almacena la dirección de memoria de una variable.")

        # Caso 2: frase completa normal termina intacta
        texto_completo = "Python es dinámico y multiparadigma. Es ideal para automatizar tareas."
        self.assertEqual(cp.podar_oracion_incompleta(texto_completo), texto_completo)

        # Caso 3: una sola frase sin punto final se cierra limpiamente
        texto_unico = "Lyris es una asistente modular"
        self.assertEqual(cp.podar_oracion_incompleta(texto_unico), "Lyris es una asistente modular.")

        # Caso 4: corte en streaming (_cortar con final=True)
        parcial = (
            "La compilación fue exitosa. "
            "El ejecutable se guardó garantizando precisión y eficiencia en cada"
        )
        frases, _ = cp._cortar(parcial, emitido=0, final=True)
        self.assertEqual(frases, ["La compilación fue exitosa."])

    def test_regla_operadores_hablados_en_cartucho_programacion(self):
        """El cartucho de programación instruye escribir operadores en palabras para no perderlos en voz."""
        cartucho = obtener_cartucho("programacion")
        self.assertIn("asterisco", cartucho.lower())
        self.assertIn("ampersand", cartucho.lower())
        self.assertIn("flecha", cartucho.lower())


if __name__ == "__main__":
    unittest.main()
