"""Regresión: Google Workspace, agente y vigilante proactivo."""
import os
import tempfile
import time
import unittest
from contextlib import closing
from unittest.mock import MagicMock, patch

import agente_herramientas as ag
import google_workspace as gw
import google_workspace_oauth as oauth
import memoria_persistente as mp
import vigilante_proactivo as vig


def _mocks():
    """Clientes simulados de Calendar, Gmail y Drive (sin red)."""
    calendario = MagicMock()
    calendario.events.return_value.list.return_value.execute.return_value = {
        "items": [{"summary": "Entrega Programación I",
                   "description": "Parcial",
                   "start": {"dateTime": "2026-11-24T10:00:00-05:00"}}]}
    calendario.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt1", "htmlLink": "https://calendar.google.com/evt1"}
    gmail = MagicMock()
    mensajes = gmail.users.return_value.messages.return_value
    mensajes.list.return_value.execute.return_value = {"messages": [{"id": "m1"}]}
    mensajes.get.return_value.execute.return_value = {
        "snippet": "Traigan la entrega del parcial",
        "payload": {"headers": [
            {"name": "From", "value": "Profesor <profe@universidad.com>"},
            {"name": "Subject", "value": "Entrega Programación I"}]}}
    drive = MagicMock()
    drive.files.return_value.list.return_value.execute.return_value = {"files": [
        {"id": "f1", "name": "Guía Programación I",
         "mimeType": "application/vnd.google-apps.document",
         "webViewLink": "https://drive.google.com/file/f1"}]}
    return calendario, gmail, drive


class TestGoogleWorkspace(unittest.TestCase):
    def setUp(self):
        gw.reiniciar()
        vig.reiniciar()

    def tearDown(self):
        gw.reiniciar()
        vig.reiniciar()

    def test_degradacion_limpia_sin_credenciales(self):
        with patch.object(oauth, "librerias", return_value=None):
            pruebas = (
                (gw.agenda_hoy, ()),
                (gw.crear_evento_calendario, ("Entrega", "2026-11-24T10:00:00")),
                (gw.resumen_correos, ()),
                (gw.buscar_drive, ("Programación",)),
                (gw.autorizar_google, ()),
            )
            for funcion, argumentos in pruebas:
                with self.subTest(funcion=funcion.__name__):
                    resultado = funcion(*argumentos)
                    self.assertFalse(resultado["ok"])
                    self.assertIn("Google Workspace", resultado["texto"])

    def test_agenda_y_creacion_de_eventos(self):
        calendario, gmail, drive = _mocks()
        gw.set_servicios_mock(calendario=calendario, gmail=gmail, drive=drive)
        agenda = gw.agenda_hoy(2)
        self.assertTrue(agenda["ok"])
        self.assertEqual(len(agenda["eventos"]), 1)
        self.assertEqual(agenda["eventos"][0]["titulo"], "Entrega Programación I")
        self.assertNotEqual(agenda["eventos"][0]["hora"], "hora por definir")
        creado = gw.crear_evento_calendario("Entrega Parcial", "2026-11-24T10:00:00", 45)
        self.assertTrue(creado["ok"])
        self.assertIn("Entrega Parcial", creado["texto"])
        cuerpo = calendario.events.return_value.insert.call_args.kwargs["body"]
        self.assertEqual(cuerpo["summary"], "Entrega Parcial")
        self.assertIn("10:00", cuerpo["start"]["dateTime"])
        self.assertIn("10:45", cuerpo["end"]["dateTime"])

    def test_gmail_y_drive_con_cliente_simulado(self):
        calendario, gmail, drive = _mocks()
        gw.set_servicios_mock(calendario=calendario, gmail=gmail, drive=drive)
        correos = gw.resumen_correos(3)
        self.assertTrue(correos["ok"])
        self.assertEqual(len(correos["correos"]), 1)
        self.assertIn("Profesor", correos["texto"])
        self.assertIn("Entrega Programación I", correos["texto"])
        archivos = gw.buscar_drive("Programación", 3)
        self.assertTrue(archivos["ok"])
        self.assertIn("Guía Programación I", archivos["texto"])
        self.assertIn("https://drive.google.com", archivos["archivos"][0]["enlace"])
        self.assertIn("Programación", drive.files.return_value.list.call_args.kwargs["q"])


class TestAgenteWorkspace(unittest.TestCase):
    def setUp(self):
        gw.reiniciar()
        vig.reiniciar()

    def tearDown(self):
        gw.reiniciar()
        vig.reiniciar()

    def test_catalogo_intenciones_y_etiquetas(self):
        for nombre in ("agenda_hoy", "crear_evento", "resumen_correos", "buscar_drive"):
            self.assertIn(nombre, ag.CATALOGO)
        casos = {
            "¿qué tengo en mi agenda?": "agenda_hoy",
            "agenda una entrega para mañana": "crear_evento",
            "revisa mis correos": "resumen_correos",
            "busca en mi drive la guía": "buscar_drive",
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                nombres = [nombre for nombre, _ in ag.detectar_intencion(texto)]
                self.assertIn(esperado, nombres)
                self.assertIsNotNone(ag.responder_directo(texto))
        self.assertEqual(ag.parsear_tags("[[TOOL:agenda_hoy|2]]"), [("agenda_hoy", "2")])
        self.assertEqual(ag.parsear_tags("[[TOOL:resumen_correos|]]"),
                         [("resumen_correos", "")])

    def test_bucle_encadena_herramientas_google(self):
        calendario, gmail, drive = _mocks()
        gw.set_servicios_mock(calendario=calendario, gmail=gmail, drive=drive)
        resultado = ag.ejecutar_bucle(
            "[[TOOL:agenda_hoy|2]] [[TOOL:buscar_drive|Programación]]")
        self.assertEqual(set(resultado["herramientas"]),
                         {"agenda_hoy", "buscar_drive"})
        self.assertEqual(len(resultado["datos"]), 2)
        self.assertIn("Entrega Programación I", resultado["datos"][0]["resultado"])
        self.assertNotIn("[[TOOL", resultado["respuesta"])

    def test_memoria_sqlite_se_preserva(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        ruta = os.path.join(temporal.name, "memoria_jarvis.db")
        with patch.object(mp, "RUTA_DB", ruta):
            mp.guardar_recuerdo("tarea", "entrega_prog", "Entrega de Programación I mañana")
            self.assertIn("Programación I", ag.ejecutar("buscar_memoria", "Programación"))
            with closing(mp._conectar()) as con:
                fila = con.execute("SELECT valor FROM recuerdos WHERE clave=?",
                                   ("entrega_prog",)).fetchone()
            self.assertIsNotNone(fila)
            self.assertIn("Programación I", fila["valor"])


class TestVigilanteProactivo(unittest.TestCase):
    def setUp(self):
        gw.reiniciar()
        vig.reiniciar()

    def tearDown(self):
        gw.reiniciar()
        vig.reiniciar()

    def test_alerta_de_hardware_y_cooldown_de_20_minutos(self):
        bateria_baja = {"disponible": True, "porcentaje": 12,
                        "cargando": False, "segundos_restantes": None}
        bateria_normal = {"disponible": True, "porcentaje": 80,
                          "cargando": True, "segundos_restantes": None}
        con_memoria_vacia = (
            patch("recordatorios._cargar", return_value=[]),
            patch.object(mp, "listar_recuerdos", return_value=[]),
            patch.object(gw, "agenda_hoy",
                         return_value={"ok": False, "texto": "sin autorizar"}),
        )
        for parche in con_memoria_vacia:
            parche.start()
            self.addCleanup(parche.stop)
        with patch("telemetria.estado_bateria", return_value=bateria_baja), \
             patch("telemetria.metricas", return_value=(10, 95)):
            primero = vig.contexto_para_prompt("hola", ahora=1000.0)
            self.assertIn("batería", primero)
            self.assertEqual(vig.contexto_para_prompt("hola", ahora=1100.0), "")
            self.assertIsNone(vig.evaluar("hola", ahora=1300.0, forzar=True))
            with patch("telemetria.estado_bateria", return_value=bateria_normal):
                tercero = vig.contexto_para_prompt("hola", ahora=2500.0)
        self.assertIn("RAM", tercero)
        self.assertNotIn("batería", tercero)

    def test_entrega_proxima_desde_memoria(self):
        ahora = time.time()
        with patch("recordatorios._cargar", return_value=[]), \
             patch.object(mp, "listar_recuerdos", return_value=[
                 {"categoria": "tarea", "valor": "Entrega de Programación I mañana"}]), \
             patch("recordatorios.parsear_tiempo",
                   return_value=(ahora + 20 * 60, "20:00", "Entrega")), \
             patch.object(gw, "agenda_hoy",
                          return_value={"ok": False, "texto": "sin autorizar"}), \
             patch("telemetria.estado_bateria", return_value={"disponible": False}), \
             patch("telemetria.metricas", return_value=(10, 30)):
            aviso = vig.evaluar("hola", ahora=ahora, forzar=True)
        self.assertIsNotNone(aviso)
        self.assertEqual(aviso["tipo"], "entrega")
        self.assertIn("Programación I", aviso["mensaje"])

    def test_inyeccion_en_cerebro_solo_para_dueno(self):
        import cerebro as cerebro_mod

        capturado = {}

        def falso_prompt(memoria, texto, historial, **kw):
            capturado.update(kw)
            return "prompt-de-prueba"

        cerebro = object.__new__(cerebro_mod.Cerebro)
        cerebro.turno_invitado = False
        cerebro.app = None
        cerebro._seguimiento_visual_pendiente = False
        cerebro.memoria = object()
        cerebro._obtener_historial_podado = lambda: []
        aviso = "Aviso: batería al 12% y sin cargador."
        with patch.object(cerebro_mod, "construir_prompt", falso_prompt), \
             patch("vigilante_proactivo.contexto_para_prompt", return_value=aviso):
            cerebro.instrucciones("hola")
            self.assertIn(aviso, capturado.get("contexto_adicional", ""))
            capturado.clear()
            cerebro.turno_invitado = True
            cerebro.instrucciones("hola")
        self.assertNotIn(aviso, capturado.get("contexto_adicional", ""))


if __name__ == "__main__":
    unittest.main()
