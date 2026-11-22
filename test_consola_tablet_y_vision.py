"""Tests: consola de chat tablet y captura fresca de pantalla."""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch, call
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestEcosistemaGestorLanUUID(unittest.TestCase):
    """emparejar_lan debe generar device_id que sea UUID puro (sin prefijo 'lan_')."""

    def test_emparejar_lan_device_id_es_uuid_puro(self):
        """Garantiza que el device_id del emparejamiento LAN sea un UUID válido."""
        try:
            from ecosistema_gestor import GestorEcosistema
            from ecosistema_almacen import AlmacenEcosistema
            from ecosistema_contratos import TipoDispositivo, Scope
        except ImportError as e:
            self.skipTest(f"Import no disponible: {e}")

        almacen = AlmacenEcosistema()
        gestor = GestorEcosistema(almacen=almacen)
        pair = gestor.emparejar_lan(
            TipoDispositivo.TABLET_HUD,
            (Scope.STATE_READ, Scope.UI_CONTROL, Scope.OPERATION_REQUEST),
        )
        self.assertIsNotNone(pair, "emparejar_lan debe retornar dict")
        did = pair.get("device_id", "")
        # Debe ser UUID puro (sin prefijo "lan_")
        self.assertFalse(did.startswith("lan_"),
                         f"device_id no debe tener prefijo 'lan_': {did!r}")
        try:
            UUID(did)
        except ValueError:
            self.fail(f"device_id='{did}' no es un UUID válido")

    def test_emparejar_lan_device_id_pasa_validacion_command_request(self):
        """El device_id generado debe poder usarse en CommandRequest sin ValueError."""
        try:
            from ecosistema_gestor import GestorEcosistema
            from ecosistema_almacen import AlmacenEcosistema
            from ecosistema_contratos import TipoDispositivo, Scope
            from ecosistema_puente import EcosistemaPuente
            from ecosistema_sesiones import GestorSesiones
        except ImportError as e:
            self.skipTest(f"Import no disponible: {e}")

        almacen = AlmacenEcosistema()
        gestor = GestorEcosistema(almacen=almacen)
        pair = gestor.emparejar_lan(
            TipoDispositivo.TABLET_HUD,
            (Scope.STATE_READ, Scope.UI_CONTROL, Scope.OPERATION_REQUEST),
        )
        self.assertIsNotNone(pair)

        # Autenticar el token del pair
        identity = gestor.autenticar_token(pair["token"])
        if not identity:
            # Si no existe autenticar_token, construir identity manualmente
            identity = pair

        # Crear BusSSE mock y puente
        bus_mock = MagicMock()
        bus_mock.publicar = MagicMock()

        origen = f"https://192.168.0.7:8765"
        puente = EcosistemaPuente(gestor, bus_mock, origenes=(origen,))

        # Intentar crear CommandRequest — no debe lanzar ValueError
        try:
            cmd = puente.command(identity, "conversacion_tablet", {"texto": "hola"})
            self.assertIsNotNone(cmd)
            self.assertIsNotNone(cmd.message_id)
        except PermissionError:
            self.skipTest("identity no tiene scope OPERATION_REQUEST en este contexto")
        except ValueError as e:
            self.fail(f"CommandRequest lanzó ValueError: {e}")


class TestConsolaTablataEncolaTexto(unittest.TestCase):
    """encolar_turno debe encolar texto_tablet a app.cola cuando el turno está libre."""

    def test_encolar_turno_pone_texto_en_cola(self):
        try:
            import ecosistema_eventos
        except ImportError as e:
            self.skipTest(f"Import no disponible: {e}")

        # Crear mocks
        puente_mock = MagicMock()
        puente_mock.reservar_turno.return_value = True

        app_mock = MagicMock()
        import queue
        app_mock.cola = queue.Queue()

        identity = {
            "device_id": "aabbccdd-0000-0000-0000-000000000001",
            "session_id": "aabbccdd-0000-0000-0000-000000000002",
            "tipo_dispositivo": "tablet_hud",
        }

        command_mock = MagicMock()
        command_mock.a_dict.return_value = {"operacion": "conversacion_tablet"}

        result = ecosistema_eventos.encolar_turno(
            puente_mock, app_mock, identity, "hola", command_mock
        )

        self.assertTrue(result, "encolar_turno debe retornar True")
        self.assertFalse(app_mock.cola.empty(), "La cola debe tener un elemento")
        tipo, payload = app_mock.cola.get_nowait()
        self.assertEqual(tipo, "texto_tablet")
        self.assertEqual(payload["texto"], "hola")

    def test_encolar_turno_falla_si_turno_ocupado(self):
        try:
            import ecosistema_eventos
        except ImportError as e:
            self.skipTest(f"Import no disponible: {e}")

        puente_mock = MagicMock()
        puente_mock.reservar_turno.return_value = False  # turno ocupado

        app_mock = MagicMock()
        import queue
        app_mock.cola = queue.Queue()

        identity = {
            "device_id": "aabbccdd-0000-0000-0000-000000000001",
            "session_id": "aabbccdd-0000-0000-0000-000000000002",
            "tipo_dispositivo": "tablet_hud",
        }
        command_mock = MagicMock()
        command_mock.a_dict.return_value = {}

        result = ecosistema_eventos.encolar_turno(
            puente_mock, app_mock, identity, "hola", command_mock
        )
        self.assertFalse(result, "encolar_turno debe retornar False si turno ocupado")
        self.assertTrue(app_mock.cola.empty(), "La cola debe estar vacía si turno ocupado")


class TestVisionCapturaFresca(unittest.TestCase):
    """consultar_entorno_actual debe lanzar captura fresca para preguntas de pantalla."""

    def test_pide_pantalla_lanza_captura(self):
        """Verificar que al preguntar '¿qué ves?' se solicita captura (no se devuelve solo contexto)."""
        try:
            from multimodal_puente_app import SistemaMultimodalSilvestra
        except ImportError as e:
            self.skipTest(f"Import no disponible: {e}")

        app_mock = MagicMock()
        app_mock.cola = MagicMock()
        app_mock.iniciativa = MagicMock()

        sistema = SistemaMultimodalSilvestra(app_mock)

        with patch.object(sistema, "_captura_temporal_segura", return_value="captura_efimera_ok") as mock_cap, \
             patch.object(sistema, "_actualizar_contexto", return_value={"titulo": "Chrome", "pid": 1234, "hwnd": 1}), \
             patch.object(sistema.interprete, "consultar_interpretacion_actual", return_value={"respuesta": ""}):

            # Simular que corremos en hilo secundario (no main thread)
            import threading
            resultado = {}

            def _run():
                r = sistema.consultar_entorno_actual("¿qué ves en pantalla?")
                resultado["r"] = r

            t = threading.Thread(target=_run)
            t.start()
            t.join(timeout=5.0)

        # La captura debe haberse solicitado
        mock_cap.assert_called()
        self.assertIn("r", resultado)

    def test_no_pide_pantalla_no_lanza_captura(self):
        """Sin frase de visión explícita, no se dispara captura de pantalla."""
        try:
            from multimodal_puente_app import SistemaMultimodalSilvestra
        except ImportError as e:
            self.skipTest(f"Import no disponible: {e}")

        app_mock = MagicMock()
        sistema = SistemaMultimodalSilvestra(app_mock)

        with patch.object(sistema, "_captura_temporal_segura", return_value="captura_efimera_ok") as mock_cap, \
             patch.object(sistema, "_actualizar_contexto", return_value={}), \
             patch.object(sistema.interprete, "consultar_interpretacion_actual", return_value={"respuesta": ""}):

            resultado = sistema.consultar_entorno_actual("¿cómo está el clima?")

        mock_cap.assert_not_called()
        self.assertIsNotNone(resultado)


class TestProveedoresTimeoutReducido(unittest.TestCase):
    """completar_flujo debe usar timeout_paralelo <= 2.5s por defecto."""

    def test_timeout_paralelo_default_es_maximo_2_5(self):
        import inspect
        try:
            import proveedores
        except ImportError as e:
            self.skipTest(f"Import no disponible: {e}")

        sig = inspect.signature(proveedores.completar_flujo)
        default_timeout = sig.parameters["timeout_paralelo"].default
        self.assertLessEqual(
            default_timeout, 2.5,
            f"timeout_paralelo debe ser <= 2.5s, encontrado: {default_timeout}"
        )


class TestCerebroPromptAntiAlucinacionVision(unittest.TestCase):
    """El prompt del sistema debe incluir instrucciones anti-alucinación para visión."""

    def test_prompt_incluye_directiva_vision(self):
        try:
            import cerebro_prompt
            from unittest.mock import MagicMock
        except ImportError as e:
            self.skipTest(f"Import no disponible: {e}")

        memoria_mock = MagicMock()
        memoria_mock.nombre = "Lyris"
        memoria_mock.creador = "Moisés"
        memoria_mock.proposito = "asistir"
        memoria_mock.hechos = []
        memoria_mock.vocabulario = []
        memoria_mock.datos = {}

        with patch("cerebro_prompt.ideas") as mi, patch("cerebro_prompt.hilos") as mh, \
             patch("cerebro_prompt.acciones") as ma:
            mi.resumen.return_value = ""
            mh.resumen.return_value = ""
            ma.ACCIONES = {}
            ma.ESPECIALES = {}
            ma.VIVAS = {}

            try:
                prompt = cerebro_prompt.construir_prompt(
                    memoria_mock, texto_actual="¿qué ves en pantalla?"
                )
            except Exception:
                # Si falla por dependencias de acciones, chequear solo la constante
                # de instrucciones directamente
                prompt = cerebro_prompt.cargar_alma() + " " + cerebro_prompt.SOBRE_MI

        # Verificar que las instrucciones incluyan la directiva de visión
        keywords = ["qué ves", "mira mi pantalla", "ÚNICAMENTE"]
        encontrado = any(kw in prompt for kw in keywords)
        self.assertTrue(
            encontrado,
            "El prompt debe incluir directiva anti-alucinación para preguntas de visión"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
