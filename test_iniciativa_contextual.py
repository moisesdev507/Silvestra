"""Suite de pruebas para el motor de iniciativa contextual (Etapa 5)."""
from __future__ import annotations

import threading
import time
import unittest
from typing import Any

import iniciativa_contextual as ic


class MockApp:
    def __init__(self, puede_hablar: bool = True, descansando: bool = False):
        self._puede_hablar = puede_hablar
        self.descansando = descansando
        self.cola = []
        self.memoria = type("Memoria", (), {"nombre": "Silvestra", "creador": "Moisés", "hechos": []})()
        self.cerebro = type("Cerebro", (), {"_pedir": lambda msgs: "Hola Moisés, ¿cómo va todo?"})()

    def puede_hablar_sola(self) -> bool:
        return self._puede_hablar


def _crear_contexto_base(
    ts: float,
    modo: str = "normal",
    ausente: bool = False,
    recs: list | None = None,
    sesion_continua: bool = False,
    conf_sesion: float = 0.8,
    actividad: str = "programando",
    conf_act: float = 0.8,
) -> dict[str, Any]:
    return {
        "timestamp": ts,
        "detectado": {
            "fuentes_estado": {"windows": "ok", "presencia": "ok", "modos_sistema": "ok"},
            "modo_sistema": {"modo": modo, "etiqueta": modo.capitalize()},
            "presencia": {"activa": True, "ausente": ausente},
            "recordatorios": {
                "total_pendientes": len(recs or []),
                "proximos": recs or [],
            },
            "ventana": {"ejecutable": "Code.exe", "inactividad_seg": 30.0},
        },
        "probable": {
            "sesion_continua": {"valor": sesion_continua, "confianza": conf_sesion},
            "actividad": {"valor": actividad, "confianza": conf_act},
            "proyecto": {"valor": "Silvestra"},
        },
        "confirmado": {},
    }


class TestIniciativaContextual(unittest.TestCase):
    def setUp(self):
        self.motor = ic.MotorIniciativaContextual()
        # Fijar hora diurna estable (15:00)
        self.t_base = 1700000000.0  # asumimos timestamp base
        # Asegurar silencio de 30 min (1800s)
        self.motor._ultima_interaccion_ts = self.t_base - 1800.0

    def test_ausencia_usuario_aborta(self):
        app = MockApp()
        ctx = _crear_contexto_base(self.t_base, ausente=True)
        sug = self.motor.evaluar_oportunidad(app, contexto=ctx, t_ahora=self.t_base)
        self.assertIsNone(sug, "Debe abortar si el usuario está ausente.")

    def test_modo_restringido_bloquea_casual_y_permite_recordatorio(self):
        app = MockApp()
        # En modo estudio sin recordatorio: debe retornar None
        ctx_estudio = _crear_contexto_base(self.t_base, modo="estudio")
        sug1 = self.motor.evaluar_oportunidad(app, contexto=ctx_estudio, t_ahora=self.t_base)
        self.assertIsNone(sug1, "Modo estudio debe bloquear iniciativa casual.")

        # En modo estudio con recordatorio pendiente: debe permitir prioridad alta
        ctx_rec = _crear_contexto_base(
            self.t_base,
            modo="estudio",
            recs=[{"texto": "Entrega de proyecto", "hora": "4:00 p. m."}],
        )
        sug2 = self.motor.evaluar_oportunidad(app, contexto=ctx_rec, t_ahora=self.t_base)
        self.assertIsNotNone(sug2, "Modo estudio debe permitir recordatorios de alta prioridad.")
        self.assertEqual(sug2.prioridad, "alta")
        self.assertEqual(sug2.tema, "recordatorio")
        self.assertEqual(sug2.emocion_sugerida, "atenta")

    def test_sesion_continua_umbral_confianza(self):
        app = MockApp()
        # Confianza baja (0.50 < 0.65): no debe disparar sugerencia de sesion_continua
        ctx_baja = _crear_contexto_base(self.t_base, sesion_continua=True, conf_sesion=0.50)
        sug_baja = self.motor.evaluar_oportunidad(app, contexto=ctx_baja, t_ahora=self.t_base)
        if sug_baja:
            self.assertNotEqual(sug_baja.tema, "sesion_continua")

        # Confianza alta (0.85 >= 0.65): debe disparar sesion_continua
        self.motor._sugerencia_pendiente = None
        ctx_alta = _crear_contexto_base(self.t_base, sesion_continua=True, conf_sesion=0.85)
        sug_alta = self.motor.evaluar_oportunidad(app, contexto=ctx_alta, t_ahora=self.t_base)
        self.assertIsNotNone(sug_alta)
        self.assertEqual(sug_alta.tema, "sesion_continua")
        self.assertEqual(sug_alta.prioridad, "media")

    def test_cooldown_global_y_por_tema(self):
        app = MockApp()
        ctx = _crear_contexto_base(self.t_base, sesion_continua=True, conf_sesion=0.85)
        sug = self.motor.evaluar_oportunidad(app, contexto=ctx, t_ahora=self.t_base)
        self.assertIsNotNone(sug)

        # Emitir la sugerencia
        self.motor.marcar_emitida(sug, t_ahora=self.t_base)
        self.assertEqual(sug.estado, "emitida")

        # Evaluar 5 minutos después (dentro del cooldown global de 15 min): debe ser None
        t_5min = self.t_base + 300.0
        ctx_nuevo = _crear_contexto_base(t_5min, sesion_continua=True, conf_sesion=0.85)
        self.assertIsNone(self.motor.evaluar_oportunidad(app, contexto=ctx_nuevo, t_ahora=t_5min))

        # Evaluar 20 minutos después (supera cooldown global de 15m, pero tema sesion_continua sigue en cooldown de 45m)
        t_20min = self.t_base + 1200.0
        self.motor._ultima_interaccion_ts = t_20min - 1800.0
        ctx_20min = _crear_contexto_base(t_20min, sesion_continua=True, conf_sesion=0.85)
        sug_otra = self.motor.evaluar_oportunidad(app, contexto=ctx_20min, t_ahora=t_20min)
        # Debe saltar sesion_continua y ofrecer otra cosa (como actividad o casual)
        if sug_otra:
            self.assertNotEqual(sug_otra.tema, "sesion_continua")

    def test_revalidacion_cancelacion_si_usuario_habla_o_ausente(self):
        app = MockApp()
        ctx = _crear_contexto_base(self.t_base, sesion_continua=True, conf_sesion=0.85)
        sug = self.motor.evaluar_oportunidad(app, contexto=ctx, t_ahora=self.t_base)
        self.assertIsNotNone(sug)

        # Usuario comienza a hablar (app no puede hablar sola)
        app._puede_hablar = False
        valido, motivo = self.motor.revalidar_sugerencia(sug, app, contexto_actual=ctx, t_ahora=self.t_base)
        self.assertFalse(valido)
        self.assertEqual(motivo, "usuario_ocupado")
        self.assertEqual(sug.estado, "cancelada")

    def test_revalidacion_cancelacion_si_contexto_desactualizado(self):
        app = MockApp()
        ctx_fresco = _crear_contexto_base(self.t_base, sesion_continua=True, conf_sesion=0.85)
        sug = self.motor.evaluar_oportunidad(app, contexto=ctx_fresco, t_ahora=self.t_base)
        self.assertIsNotNone(sug)

        # Contexto envejecido 25 segundos (> 20s umbral staleness)
        ctx_viejo = _crear_contexto_base(self.t_base - 25.0)
        valido, motivo = self.motor.revalidar_sugerencia(sug, app, contexto_actual=ctx_viejo, t_ahora=self.t_base)
        self.assertFalse(valido)
        self.assertEqual(motivo, "contexto_desactualizado")
        self.assertEqual(sug.estado, "cancelada")

    def test_supervision_y_cancelacion_manual(self):
        app = MockApp()
        ctx = _crear_contexto_base(self.t_base, sesion_continua=True, conf_sesion=0.85)
        sug = self.motor.evaluar_oportunidad(app, contexto=ctx, t_ahora=self.t_base)
        self.assertIsNotNone(sug)

        estado = self.motor.obtener_estado_iniciativa(t_ahora=self.t_base)
        self.assertIsNotNone(estado.get("sugerencia_pendiente"))

        # Cancelación manual
        cancelado = self.motor.cancelar_pendiente("cancelacion_por_test")
        self.assertTrue(cancelado)
        self.assertEqual(sug.estado, "cancelada")
        self.assertEqual(sug.motivo_cancelacion, "cancelacion_por_test")

        estado_post = self.motor.obtener_estado_iniciativa(t_ahora=self.t_base)
        self.assertIsNone(estado_post.get("sugerencia_pendiente"))

    def test_concurrencia_hilo_segura(self):
        app = MockApp()
        ctx = _crear_contexto_base(self.t_base, sesion_continua=True, conf_sesion=0.85)
        errores = []

        def worker(idx: int):
            try:
                for i in range(50):
                    t = self.t_base + i * 10
                    self.motor.registrar_interaccion_usuario(t)
                    self.motor.evaluar_oportunidad(app, contexto=ctx, t_ahora=t)
                    self.motor.obtener_estado_iniciativa(t_ahora=t)
            except Exception as e:
                errores.append(e)

        hilos = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        self.assertEqual(len(errores), 0, f"Errores en concurrencia: {errores}")


if __name__ == "__main__":
    unittest.main()
