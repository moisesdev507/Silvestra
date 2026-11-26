"""Pruebas de la Fase 3 del Cerebro Único (reposo y gatekeeper compartido)."""
import contextlib
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cerebro_autonomo
import cerebro_proactivo
import cerebro_unico
import contexto_ambiental
import correcciones
import cerebro_grafo
import cerebro_trabajo
import estado_emocional_kaya
import iniciativa_unificada
import memoria
import memoria_contexto


class TestCerebroFase3(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = os.path.join(self.tmp.name, "memoria.db")
        self.parches = [
            patch.dict(os.environ, {"SILVESTRA_MEMORIA_DB": self.db}),
            patch.object(estado_emocional_kaya, "RUTA_DB",
                         os.path.join(self.tmp.name, "emocional.db")),
        ]
        for parche in self.parches:
            parche.start()
        self.memoria_anterior = memoria._memoria_instancia
        self.memoria = memoria.Memoria(
            ruta_db=self.db,
            ruta_json=os.path.join(self.tmp.name, "memoria.json"))
        self.app = SimpleNamespace(
            memoria=self.memoria, cola=MagicMock(), coordinador_live=None,
            modo_privado=False, hablando=False, escuchando=False)
        cerebro_autonomo.configurar_app(self.app)
        self.motor = cerebro_proactivo.obtener_motor_proactivo()
        self.estado_motor = (self.motor.ultimo_aviso, self.motor.arranque_ts,
                             self.motor.ultimo_sueno_ts)
        self._reset()
        con = sqlite3.connect(self.db, timeout=3)
        con.execute("CREATE TABLE IF NOT EXISTS prueba_viva (id INTEGER PRIMARY KEY, ts REAL)")
        con.commit()
        con.close()

    def tearDown(self):
        for nombre, valor in zip(("ultimo_aviso", "arranque_ts", "ultimo_sueno_ts"),
                                 self.estado_motor):
            setattr(self.motor, nombre, valor)
        memoria._memoria_instancia = self.memoria_anterior
        cerebro_autonomo.configurar_app(None)
        for parche in reversed(self.parches):
            parche.stop()
        self.tmp.cleanup()

    def _reset(self):
        cerebro_autonomo.reiniciar()
        iniciativa_unificada.reiniciar()
        self.motor.ultimo_aviso = 0.0
        self.motor.arranque_ts = time.time() - 3600.0
        self.motor.ultimo_sueno_ts = time.time()

    @staticmethod
    def _insertar(con, texto, confianza=0.6):
        con.execute(
            "INSERT INTO recuerdos(tipo_memoria,contenido,contenido_norm,origen,"
            "confianza,creado_en,actualizado_en) VALUES(?,?,?,?,?,?,?)",
            ("semantica", texto, texto.lower(), "explicito", confianza,
             "2026-11-20T10:00:00", "2026-11-20T10:00:00"))

    def _esperar(self, timeout=8.0):
        fin = time.time() + timeout
        while time.time() < fin:
            with cerebro_autonomo._bloqueo:
                if not cerebro_autonomo._consolidando:
                    return True
            time.sleep(0.02)
        return False

    def test_a_consolidacion_en_reposo_sin_bloqueo_ni_duplicados(self):
        con = self.memoria.almacen.conexion
        base = "Alpha beta gamma delta epsilon zeta eta theta"
        self._insertar(con, base)
        self._insertar(con, base + " extra")
        self._insertar(con, "Delta likes hiking on weekends")
        self._insertar(con, "Delta likes reading on weekends")
        con.commit()
        capturas = []
        real = cerebro_autonomo._consolidar

        def capturar(uid, ruta, app):
            resultado = real(uid, ruta, app)
            capturas.append(resultado)
            return resultado

        inicio = time.time()
        with patch.object(cerebro_autonomo, "_consolidar", side_effect=capturar):
            self.assertTrue(cerebro_autonomo.ejecutar_consolidacion_reposo(forzar=True))
        self.assertLess(time.time() - inicio, 0.5)
        self.assertTrue(self._esperar())
        self.assertTrue(capturas)
        self.assertGreaterEqual(capturas[0]["pasos"], 2)
        # SQLite sigue aceptando escrituras mientras el daemon trabajaba.
        viva = sqlite3.connect(self.db, timeout=3)
        viva.execute("INSERT INTO prueba_viva(ts) VALUES(?)", (time.time(),))
        viva.commit()
        viva.close()
        filas = con.execute(
            "SELECT id,contenido,estado,reemplaza_a_id,confianza FROM recuerdos "
            "WHERE contenido LIKE 'Alpha beta%'").fetchall()
        duplicados = [f for f in filas if f["estado"] == "consolidado"]
        activos = [f for f in filas if f["estado"] == "activo"]
        self.assertEqual(len(duplicados), 1)
        self.assertTrue(all(f["reemplaza_a_id"] for f in duplicados))
        self.assertEqual(len(activos), 1)
        self.assertGreater(activos[0]["confianza"], 0.6)
        with sqlite3.connect(self.db) as check:
            resumenes = check.execute("SELECT COUNT(*) FROM memoria_resumenes").fetchone()[0]
        self.assertGreaterEqual(resumenes, 1)
        self.assertEqual(cerebro_autonomo.ejecutar_consolidacion_reposo(), False)

    def test_a2_hook_de_actividad_dispara_consolidacion(self):
        with patch.object(cerebro_autonomo, "ejecutar_consolidacion_reposo",
                          return_value=True) as disparar:
            for _ in range(5):
                self.assertFalse(cerebro_autonomo.notificar_actividad("live"))
            self.assertTrue(cerebro_autonomo.notificar_actividad("celeste"))
        disparar.assert_called_once_with()

    def test_b_gatekeeper_cooldown_y_entrega_celeste(self):
        aviso = {"tipo": "recordatorio", "mensaje": "Revisa el proyecto", "emocion": "calida"}
        with patch.object(iniciativa_unificada, "obtener_aviso", return_value=aviso), \
             patch.object(estado_emocional_kaya, "resumen_estado_emocional",
                          return_value="Ánimo: cómplice y relajada"):
            ok, detalle = cerebro_autonomo.evaluar_atencion_proactiva("recordatorio")
            self.assertTrue(ok)
            self.assertIn("Ánimo", detalle)
            self.app.cola.put.assert_called_once()
            paquete = self.app.cola.put.call_args[0][0]
            self.assertEqual(paquete[0], "hablar")
            self.assertEqual(paquete[1][0], "Revisa el proyecto")
            ok2, detalle2 = cerebro_autonomo.evaluar_atencion_proactiva("recordatorio")
            self.assertFalse(ok2)
            self.assertEqual(detalle2, "cooldown_atencion")
        self.assertEqual(self.app.cola.put.call_count, 1)

    def test_b2_gatekeeper_entrega_live_y_despierta_reposo_azul(self):
        self._reset()
        puente = SimpleNamespace(dormida=True)
        sesion = SimpleNamespace(_puente_webrtc=puente)
        live = SimpleNamespace(
            esta_live_activo=MagicMock(return_value=True),
            es_modo_principal=MagicMock(return_value=False),
            enviar_orden=MagicMock(return_value=True), sesion_live=sesion)
        self.app.coordinador_live = live
        aviso = {"tipo": "seguimiento", "mensaje": "Retoma el tema", "emocion": "calida"}
        with patch.object(iniciativa_unificada, "obtener_aviso", return_value=aviso):
            ok, _ = cerebro_autonomo.evaluar_atencion_proactiva("seguimiento")
        self.assertTrue(ok)
        live.enviar_orden.assert_called_once()
        self.assertFalse(puente.dormida)
        self.app.cola.put.assert_not_called()

    def test_b3_privado_y_noche_bloquean_live_y_celeste(self):
        for canal in ("celeste", "live"):
            for modo in ("privado", "noche"):
                self._reset()
                self.app.cola.put.reset_mock()
                self.app.coordinador_live = (
                    None if canal == "celeste" else SimpleNamespace(
                        esta_live_activo=MagicMock(return_value=True),
                        es_modo_principal=MagicMock(return_value=False),
                        enviar_orden=MagicMock(return_value=True)))
                with patch.object(cerebro_proactivo, "es_modo_privado",
                                  return_value=modo == "privado"), \
                     patch.object(cerebro_proactivo, "es_modo_noche",
                                  return_value=modo == "noche"), \
                     patch.object(iniciativa_unificada, "emitir",
                                  MagicMock(return_value=True)) as emitir, \
                     patch.object(cerebro_proactivo, "evaluar_proactividad",
                                  return_value=(True, "intruso")) as evaluar:
                    ok, detalle = cerebro_autonomo.evaluar_atencion_proactiva("aviso")
                self.assertFalse(ok)
                self.assertEqual(detalle, "modo_" + modo)
                emitir.assert_not_called()
                evaluar.assert_not_called()
                self.app.cola.put.assert_not_called()

    def test_c_integracion_linea_emocional_en_contexto_unico(self):
        cerebro_autonomo.reiniciar()
        con = contextlib.ExitStack()
        with con:
            con.enter_context(patch.object(
                memoria_contexto, "resumen_para_prompt", return_value="Ficha real"))
            con.enter_context(patch.object(
                cerebro_grafo, "consultar_contexto_grafo", return_value=""))
            con.enter_context(patch.object(
                correcciones, "resumen_para_prompt", return_value=""))
            con.enter_context(patch.object(
                cerebro_trabajo, "resumen_contexto_trabajo", return_value=""))
            con.enter_context(patch.object(
                contexto_ambiental, "resumen_para_prompt", return_value=""))
            con.enter_context(patch.object(
                memoria_contexto, "historial_conversacion_activa", return_value=[]))
            con.enter_context(patch.object(
                estado_emocional_kaya, "resumen_estado_emocional",
                return_value="Ánimo: cómplice y relajada"))
            texto = cerebro_unico.compilar_contexto_unico("hola", max_chars=2200)
            corto = cerebro_unico.compilar_contexto_unico("hola", max_chars=240)
        self.assertIn("[Estado emocional y atención]", texto)
        self.assertEqual(texto.count("Ánimo: cómplice y relajada"), 1)
        self.assertLessEqual(len(texto), 2200)
        self.assertIn("Ánimo: cómplice y relajada", corto)
        self.assertIs(cerebro_unico.evaluar_atencion_proactiva,
                      cerebro_autonomo.evaluar_atencion_proactiva)
        self.assertIs(cerebro_unico.ejecutar_consolidacion_reposo,
                      cerebro_autonomo.ejecutar_consolidacion_reposo)


if __name__ == "__main__":
    unittest.main(verbosity=2)
