"""Pruebas de integración segura del ecosistema remoto (datos solo temporales)."""
import ast
import json
import tempfile
import threading
import unittest
from pathlib import Path
from uuid import uuid4

from ecosistema_almacen import AlmacenEcosistema
from ecosistema_contratos import (ApprovalRequest, CommandRequest, Observation, Scope,
    TipoDispositivo, serializar_seguro)
from ecosistema_gestor import GestorEcosistema
from ecosistema_puente import EcosistemaPuente
from ecosistema_sse import BusSSE


class FakeClock:
    def __init__(self): self.now = 1000.0
    def __call__(self): return self.now


class EcosistemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = FakeClock()
        self.store = AlmacenEcosistema(Path(self.tmp.name) / "devices.json")
        self.g = GestorEcosistema(self.store, self.clock)
        self.core = self.g.registrar_local(TipoDispositivo.PC_NUCLEO,
            [Scope.STATE_READ, Scope.OPERATION_REQUEST, Scope.OPERATION_APPROVE])
        self.bus = BusSSE(capacidad=4, max_conexiones=1, max_pet=3, ventana_seg=5)
        self.bridge = EcosistemaPuente(self.g, self.bus, ["http://127.0.0.1:8765"])

    def tearDown(self): self.tmp.cleanup()

    def pair(self, kind, scopes, **kwargs):
        code = self.g.emitir_codigo(kind, scopes, **kwargs)
        return code, self.g.canjear_codigo(code)

    def test_device_types_core_unique_and_pairing_hashed(self):
        self.assertEqual(len(TipoDispositivo), 6)
        results = []
        for kind in list(TipoDispositivo)[1:]:
            _, paired = self.pair(kind, [Scope.STATE_READ], capacidades=["pantalla"], version_cliente="2.1")
            results.append(paired)
        with self.assertRaises(ValueError): self.g.registrar_local(TipoDispositivo.PC_NUCLEO)
        raw = self.store.ruta.read_text(encoding="utf-8")
        self.assertNotIn('"token":', raw); self.assertNotIn('"cookie":', raw)
        self.assertNotIn(results[0]["token"], raw); self.assertNotIn(results[0]["cookie"], raw)
        devices = self.store.cargar()["dispositivos"]
        tablet = next(x for x in devices.values() if x["tipo_dispositivo"] == "tablet_hud")
        self.assertEqual(tablet["version_cliente"], "2.1")
        self.assertEqual(tablet["capacidades"], ["pantalla"])
        with self.assertRaises(ValueError):
            self.g.emitir_codigo(TipoDispositivo.TABLET_HUD, [Scope.STATE_READ], capacidades=["memoria_central"])
        with self.assertRaises(ValueError):
            self.g.emitir_codigo(TipoDispositivo.TABLET_HUD, [Scope.OPERATION_APPROVE])

    def test_pair_single_use_expiration_and_credentials(self):
        code, result = self.pair(TipoDispositivo.TABLET_HUD, [Scope.STATE_READ])
        self.assertIsNotNone(result); self.assertIsNone(self.g.canjear_codigo(code))
        ident = self.g.autenticar_cookie(result["cookie"])
        self.assertTrue(self.g.autorizar(ident, Scope.STATE_READ))
        self.assertFalse(self.g.autorizar(ident, Scope.UI_CONTROL))
        self.assertIn("HttpOnly; SameSite=Strict", self.g.cookie_header(result["cookie"]))
        self.assertIn("; Secure", self.g.cookie_header(result["cookie"], secure=True))
        self.assertTrue(self.g.heartbeat(ident))
        self.clock.now += 3601
        self.assertFalse(self.g.autorizar(ident, Scope.STATE_READ))
        _, second = self.pair(TipoDispositivo.TABLET_HUD, [Scope.STATE_READ])
        ident2 = self.g.autenticar_cookie(second["cookie"])
        rotated = self.g.rotar_token(ident2)
        self.assertTrue(rotated); self.assertIsNotNone(self.g.autenticar_token(rotated))
        self.assertFalse(self.g.autorizar(ident2, Scope.STATE_READ))
        self.assertIsNone(self.g.rotar_token({"device_id": second["device_id"]}))

    def test_pair_code_concurrent_redemption_is_single_use(self):
        code = self.g.emitir_codigo(TipoDispositivo.TABLET_HUD, [Scope.STATE_READ])
        results = []; lock = threading.Lock()
        def run():
            value = self.g.canjear_codigo(code)
            with lock: results.append(value)
        threads = [threading.Thread(target=run) for _ in range(8)]
        [t.start() for t in threads]; [t.join(3) for t in threads]
        self.assertTrue(all(not t.is_alive() for t in threads))
        self.assertEqual(sum(bool(x) for x in results), 1)

    def test_scope_revocation_and_disconnect(self):
        _, tablet = self.pair(TipoDispositivo.TABLET_HUD, [Scope.STATE_READ])
        ident = self.g.autenticar_cookie(tablet["cookie"])
        self.clock.now += 100
        self.assertEqual(self.g.marcar_desconectados(90), [tablet["device_id"]])
        self.assertFalse(self.store.cargar()["dispositivos"][tablet["device_id"]]["conectado"])
        self.assertTrue(self.g.revocar(tablet["device_id"]))
        self.assertFalse(self.g.autorizar(ident, Scope.STATE_READ))

    def test_origin_and_cors_fail_closed(self):
        self.assertTrue(self.bridge.validar_origen("http://127.0.0.1:8765", "127.0.0.1:8765"))
        self.assertFalse(self.bridge.validar_origen("https://evil.test", "127.0.0.1:8765"))
        self.assertFalse(self.bridge.validar_origen("", "127.0.0.1:8765", mutacion=True))
        self.assertEqual(self.bridge.cors("https://evil.test", "127.0.0.1:8765"), {})
        self.assertNotIn("*", str(self.bridge.cors("http://127.0.0.1:8765", "127.0.0.1:8765")))
        expired = self.g.emitir_codigo(TipoDispositivo.TABLET_HUD, [Scope.STATE_READ], ttl_seg=1)
        self.clock.now += 2; self.assertIsNone(self.g.canjear_codigo(expired))

    def test_observation_cannot_be_command_and_payload_is_sanitized(self):
        _, paired = self.pair(TipoDispositivo.TABLET_HUD, [Scope.SENSOR_SUBMIT])
        identity = self.g.autenticar_cookie(paired["cookie"])
        obs = self.bridge.observation(identity, {"temperatura": 21})
        self.assertFalse(obs.ejecutable)
        with self.assertRaises(ValueError): self.bridge.observation(identity, {"accion": "borrar"})
        clean = serializar_seguro({"nota": "Bearer abcdef123", "token": "secret", "url": "https://u:p@host/?token=secret"})
        self.assertNotIn("abcdef123", clean); self.assertNotIn("secret", clean)

    def test_command_requires_distinct_approved_device_and_rechecks_approver(self):
        _, tablet = self.pair(TipoDispositivo.TABLET_HUD, [Scope.OPERATION_REQUEST])
        _, phone = self.pair(TipoDispositivo.TELEFONO_MOVIL, [Scope.OPERATION_APPROVE])
        requester = self.g.autenticar_cookie(tablet["cookie"])
        approver = self.g.autenticar_cookie(phone["cookie"])
        cmd = self.bridge.command(requester, "crear_respaldo", {"parametros": {}}, True)
        self.bridge.guardar_pendiente(requester, cmd)
        _, _, approval = self.bridge.aprobar_pendiente(approver, cmd.message_id)
        self.assertTrue(self.bridge.validar_ejecucion(requester, cmd, approval))
        self.g.revocar(phone["device_id"])
        self.assertFalse(self.bridge.validar_ejecucion(requester, cmd, approval))
        self.assertFalse(self.bridge.validar_ejecucion(requester, cmd, None))

    def test_remote_conversation_turn_is_serialized_by_session(self):
        _, first = self.pair(TipoDispositivo.TABLET_HUD, [Scope.STATE_READ])
        _, second = self.pair(TipoDispositivo.TELEFONO_MOVIL, [Scope.STATE_READ])
        one = self.g.autenticar_cookie(first["cookie"]); two = self.g.autenticar_cookie(second["cookie"])
        self.assertTrue(self.bridge.reservar_turno(one))
        self.assertFalse(self.bridge.reservar_turno(two))
        self.assertFalse(self.bridge.reservar_turno(two, cerrar=True))
        self.assertTrue(self.bridge.reservar_turno(one, cerrar=True))
        self.assertFalse(self.bridge.reservar_turno(two, cerrar=True))
        self.assertTrue(self.bridge.reservar_turno(two))

    def test_sensitive_approval_flows_through_central_permissions(self):
        _, tablet = self.pair(TipoDispositivo.TABLET_HUD, [Scope.OPERATION_REQUEST])
        _, phone = self.pair(TipoDispositivo.TELEFONO_MOVIL, [Scope.OPERATION_APPROVE])
        requester = self.g.autenticar_cookie(tablet["cookie"])
        approver = self.g.autenticar_cookie(phone["cookie"])
        cmd = self.bridge.command(requester, "crear_respaldo", {"parametros": {}}, True)
        self.bridge.guardar_pendiente(requester, cmd)
        _, _, approval = self.bridge.aprobar_pendiente(approver, cmd.message_id)
        class Permissions:
            def confirmar_autorizacion(self, auth, actor):
                self.assertion = (auth, actor); return {"aprobada": True}
        class Integration:
            motor_permisos = Permissions()
            def __init__(self): self.calls = 0
            def ejecutar_solicitud(self, req):
                self.calls += 1
                if self.calls == 1:
                    class Pending:
                        metadatos = {"id_autorizacion": "auth-1"}; estado = "pendiente_autorizacion"
                    return {"resultado": Pending()}
                class Done: estado = "completada"
                return {"resultado": Done()}
        class App: pass
        app = App(); app.integracion_cognitiva = Integration()
        result = self.bridge.ejecutar_controlado(app, requester, cmd, approval)
        self.assertEqual(result["estado"], "completada")
        self.assertEqual(app.integracion_cognitiva.calls, 2)

    def test_private_mode_removes_sensitive_fields(self):
        state = {"telemetria": {"cpu": 44, "microfono": "Activo"},
            "biometria": {"identidad": "dueño"}, "contexto": {"titulo": "privado"},
            "datos": {"recordatorios": [1], "notas": [2], "eventos": [3], "reloj": {"hora": "12"}},
            "silvestra": {"subtitulo": "secreto", "tarjeta": "privado"}}
        result = self.bridge.filtrar_estado(state, True)
        self.assertEqual(result["biometria"], None); self.assertEqual(result["contexto"], None)
        self.assertEqual(result["telemetria"], {"modo_privado": True})
        self.assertFalse(result["datos"]["notas"]); self.assertFalse(result["datos"]["recordatorios"])

    def test_sse_replay_reset_rate_and_connection_cap(self):
        for n in range(6): self.bus.publicar({"n": n})
        self.assertEqual([e["event"] for e in self.bus.desde(0)], ["reset"])
        self.assertEqual([e["id"] for e in self.bus.desde(4)], [5, 6])
        self.assertTrue(self.bus.permitir_peticion("x", 1))
        self.assertTrue(self.bus.permitir_peticion("x", 2))
        self.assertTrue(self.bus.permitir_peticion("x", 3))
        self.assertFalse(self.bus.permitir_peticion("x", 4))
        with self.bus.conexion():
            with self.assertRaises(ConnectionError):
                with self.bus.conexion(): pass

    def test_http_and_event_adapters_are_gated(self):
        api = Path("pantalla_remota_api.py").read_text(encoding="utf-8")
        events = Path("eventos.py").read_text(encoding="utf-8")
        helper = Path("ecosistema_eventos.py").read_text(encoding="utf-8")
        self.assertNotIn("acciones.ejecutar", api)
        self.assertIn("requiere_ejecucion", events) if "requiere_ejecucion" in events else self.assertIn("bloquear_accion_remota", helper)
        self.assertIn("device_id", events); self.assertIn("tipo_dispositivo", events)

    def test_import_graph_has_no_cycles(self):
        names = {p.stem for p in Path(".").glob("*.py") if p.stem.startswith(("ecosistema_", "pantalla_remota"))}
        graph = {}
        for name in names:
            try: tree = ast.parse(Path(name + ".py").read_text(encoding="utf-8"))
            except OSError: continue
            graph[name] = [n.module.split(".")[0] for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] in names]
            graph[name] += [a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)
                for a in n.names if a.name.split(".")[0] in names]
        def visit(node, stack, done):
            if node in stack: return False
            if node in done: return True
            return all(visit(x, stack | {node}, done) for x in graph.get(node, ())) and not done.add(node)
        for node in graph: self.assertTrue(visit(node, set(), set()), node)


if __name__ == "__main__": unittest.main()
