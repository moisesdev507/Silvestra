"""Suite de pruebas unitarias e integración para el Planificador Inteligente (Etapa 6)."""
from __future__ import annotations

import os
import tempfile
import threading
import unittest
from typing import Any

import planificador as pl
import planificador_modelo as pm


class MockCerebroExitoso:
    def _pedir(self, mensajes: list, tarea: str = "fondo") -> str:
        return """{
            "titulo": "Sistema Universitario",
            "requisitos": ["Base de datos", "Seguridad"],
            "restricciones": ["Python 3.12"],
            "preguntas_pendientes": ["¿Plazo límite?"],
            "fases": [
                {
                    "id_fase": "f1", "orden": 1, "nombre": "Fase 1", "descripcion": "Diseño",
                    "tareas": [
                        {"id_tarea": "t1", "titulo": "Diseño de modelos", "descripcion": "ERD", "importancia": 5, "urgencia": 5, "complejidad": "media", "dependencias": []},
                        {"id_tarea": "t2", "titulo": "API REST", "descripcion": "Rutas", "importancia": 4, "urgencia": 4, "complejidad": "alta", "dependencias": ["t1"]}
                    ]
                }
            ]
        }"""


class MockCerebroFallo:
    def _pedir(self, mensajes: list, tarea: str = "fondo") -> str:
        raise RuntimeError("LLM no disponible o cuota agotada")


class TestPlanificador(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_file = os.path.join(self.temp_dir, "test_planes.json")
        self._orig_archivo = pl.ARCHIVO_PLANES
        pl.ARCHIVO_PLANES = self.temp_file
        self.planif = pl.Planificador()

    def tearDown(self):
        pl.ARCHIVO_PLANES = self._orig_archivo
        if os.path.exists(self.temp_file):
            try:
                os.remove(self.temp_file)
            except Exception:
                pass
        tmp = self.temp_file + ".tmp"
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
        try:
            os.rmdir(self.temp_dir)
        except Exception:
            pass

    def test_descomposicion_compleja_sistema_universitario(self):
        prompt = "Quiero desarrollar un sistema de administración universitaria"
        plan = self.planif.crear_plan(prompt)
        self.assertIsNotNone(plan)
        self.assertIn("sistema", plan.titulo.lower())
        self.assertGreaterEqual(len(plan.fases), 3)

        # Jerarquía completa: objetivo -> fases -> tareas -> subtareas
        total_tareas = plan.todas_las_tareas()
        self.assertGreater(len(total_tareas), 4)
        tiene_subtareas = any(len(t.subtareas) > 0 for t in total_tareas)
        self.assertTrue(tiene_subtareas, "El plan debe contener subtareas desglosadas.")

        # Preguntas aclaratorias de información faltante
        self.assertGreater(len(plan.preguntas_pendientes), 0)
        self.assertTrue(any("stack" in p.lower() or "lenguaje" in p.lower() for p in plan.preguntas_pendientes))

    def test_validacion_dependencias_y_deteccion_ciclos(self):
        f1 = pm.Fase("f1", 1, "Fase 1", "desc", pm.ESTADO_PENDIENTE, [
            pm.Tarea("ta", "Tarea A", "", "f1", pm.ESTADO_PENDIENTE, dependencias=["tb"]),
            pm.Tarea("tb", "Tarea B", "", "f1", pm.ESTADO_PENDIENTE, dependencias=["tc"]),
            pm.Tarea("tc", "Tarea C", "", "f1", pm.ESTADO_PENDIENTE, dependencias=["ta"]),
        ])
        plan_ciclico = pm.PlanObjetivo("p_ciclo", "Ciclo", "test", fases=[f1])
        valido, errores = pm.validar_dependencias(plan_ciclico)
        self.assertFalse(valido)
        self.assertTrue(any("Ciclo" in e for e in errores))

        # Dependencia rota
        f2 = pm.Fase("f2", 1, "Fase 2", "desc", pm.ESTADO_PENDIENTE, [
            pm.Tarea("tx", "Tarea X", "", "f2", pm.ESTADO_PENDIENTE, dependencias=["t_fantasma"]),
        ])
        plan_roto = pm.PlanObjetivo("p_roto", "Roto", "test", fases=[f2])
        valido_r, errores_r = pm.validar_dependencias(plan_roto)
        self.assertFalse(valido_r)
        self.assertTrue(any("inexistente" in e for e in errores_r))

    def test_calculo_priorizacion_y_orden_accionables(self):
        f1 = pm.Fase("f1", 1, "Fase", "", pm.ESTADO_PENDIENTE, [
            pm.Tarea("t_baja", "Poco urgente", "", "f1", pm.ESTADO_PENDIENTE, importancia=1, urgencia=1, complejidad="alta"),
            pm.Tarea("t_alta", "Muy importante y urgente", "", "f1", pm.ESTADO_PENDIENTE, importancia=5, urgencia=5, complejidad="baja"),
        ])
        plan = pm.PlanObjetivo("p_prio", "Prio", "test", fases=[f1])
        accionables = pm.obtener_tareas_accionables(plan)
        self.assertEqual(len(accionables), 2)
        self.assertEqual(accionables[0].id_tarea, "t_alta")
        self.assertGreater(accionables[0].puntaje_prioridad, accionables[1].puntaje_prioridad)

    def test_persistencia_recuperacion_sesiones(self):
        plan = self.planif.crear_plan("Sistema contable en Python")
        id_plan = plan.id_plan

        # Segunda instancia simulando reinicio
        planif2 = pl.Planificador()
        recuperado = planif2.obtener_plan(id_plan)
        self.assertIsNotNone(recuperado)
        self.assertEqual(recuperado.titulo, plan.titulo)
        self.assertEqual(len(recuperado.fases), len(plan.fases))

    def test_actualizacion_estados_y_transiciones(self):
        plan = self.planif.crear_plan("Desarrollo de API web")
        mapa = plan.mapa_tareas()
        primera_tarea = [t for t in plan.todas_las_tareas() if not t.dependencias][0]
        tid = primera_tarea.id_tarea

        # Pasar a en_progreso
        ok, msg, _ = self.planif.actualizar_estado_tarea(plan.id_plan, tid, pm.ESTADO_EN_PROGRESO)
        self.assertTrue(ok)
        self.assertEqual(self.planif.obtener_plan(plan.id_plan).mapa_tareas()[tid].estado, pm.ESTADO_EN_PROGRESO)

        # Pasar a completada
        ok, _, _ = self.planif.actualizar_estado_tarea(plan.id_plan, tid, pm.ESTADO_COMPLETADA)
        self.assertTrue(ok)
        self.assertEqual(self.planif.obtener_plan(plan.id_plan).mapa_tareas()[tid].estado, pm.ESTADO_COMPLETADA)

    def test_bloqueo_tarea_propagacion_y_replanificacion(self):
        plan = self.planif.crear_plan("Quiero desarrollar un sistema de administración universitaria")
        # Encontrar una tarea que tenga dependientes
        mapa = plan.mapa_tareas()
        tarea_padre = None
        for t in plan.todas_las_tareas():
            hijos = [h for h in plan.todas_las_tareas() if t.id_tarea in h.dependencias]
            if hijos:
                tarea_padre = t
                break
        self.assertIsNotNone(tarea_padre)

        # Bloquear tarea padre
        ok, _, impactadas = self.planif.actualizar_estado_tarea(
            plan.id_plan, tarea_padre.id_tarea, pm.ESTADO_BLOQUEADA, "Falta aprobación de decanatura"
        )
        self.assertTrue(ok)
        self.assertGreater(len(impactadas), 0)

        # Verificar historial de cambios
        p_actual = self.planif.obtener_plan(plan.id_plan)
        self.assertTrue(any(h.tipo == "bloqueo" for h in p_actual.historial_cambios))

        # Replanificar por cambio de requisitos
        pm.replanificar_por_cambio_requisitos(p_actual, nuevos_requisitos=["Uso obligatorio de PostgreSQL 16"])
        self.assertTrue(any(h.tipo == "replanificacion" for h in p_actual.historial_cambios))

    def test_integracion_cerebro_llm_y_fallback(self):
        # Con LLM exitoso
        mock_exito = MockCerebroExitoso()
        plan_ai = self.planif.crear_plan("Sistema Universitario", cerebro=mock_exito)
        self.assertEqual(plan_ai.titulo, "Sistema Universitario")
        self.assertEqual(len(plan_ai.fases), 1)

        # Con LLM que falla -> debe activar fallback sin lanzar excepción
        mock_fallo = MockCerebroFallo()
        plan_fallback = self.planif.crear_plan("Sistema de gestión clínica", cerebro=mock_fallo)
        self.assertIsNotNone(plan_fallback)
        self.assertGreaterEqual(len(plan_fallback.fases), 3)

    def test_concurrencia_hilo_segura(self):
        plan = self.planif.crear_plan("Proyecto Concurrente")
        tid = plan.todas_las_tareas()[0].id_tarea
        errores = []

        def worker(num: int):
            try:
                for i in range(25):
                    self.planif.obtener_resumen_planes_activos()
                    self.planif.recomendar_siguiente_paso(plan.id_plan)
                    if i % 2 == 0:
                        self.planif.actualizar_estado_tarea(plan.id_plan, tid, pm.ESTADO_EN_PROGRESO)
                    else:
                        self.planif.actualizar_estado_tarea(plan.id_plan, tid, pm.ESTADO_PENDIENTE)
            except Exception as e:
                errores.append(e)

        hilos = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        self.assertEqual(len(errores), 0, f"Errores en concurrencia: {errores}")

    def test_formateo_legible_y_acciones(self):
        plan = self.planif.crear_plan("Prueba de formato")
        texto_legible = self.planif.formatear_plan_legible(plan.id_plan)
        self.assertIn("=== PLAN:", texto_legible)
        self.assertIn("Fase 1:", texto_legible)

        # Registro de acciones
        instancia = pl.instalar()
        self.assertIsNotNone(instancia)


if __name__ == "__main__":
    unittest.main()
