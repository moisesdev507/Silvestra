"""Pruebas sintéticas de contratos y seguridad del ecosistema."""
import unittest
from datetime import datetime, timezone
from uuid import uuid4

import ecosistema_contratos as c


def ids():
    return [str(uuid4()) for _ in range(4)]


def msg(cls, device, session, payload, **kw):
    mid, corr, _, _ = ids()
    args = dict(version="1.0", message_id=mid, correlation_id=corr,
                device_id=device, session_id=session,
                sent_at=datetime.now(timezone.utc).isoformat(), payload=payload)
    args.update(kw)
    return cls(**args)


class ContratosTests(unittest.TestCase):
    def test_sobres_versionados_y_validacion(self):
        d, s, _, _ = ids()
        o = msg(c.Observation, d, s, {"sensor": "estado"})
        self.assertEqual(o.kind, c.TipoMensaje.OBSERVATION)
        self.assertFalse(o.ejecutable)
        with self.assertRaises(ValueError): msg(c.Event, d, s, {"event_type": "x"}, version="2")
        with self.assertRaises(ValueError): msg(c.Event, d, s, {"event_type": "x"}, sent_at="2026-01-01T10:00:00")
        with self.assertRaises(ValueError): msg(c.Event, "bad", s, {"event_type": "x"})
        for cls, payload in ((c.CommandRequest, {"operacion": "abrir"}),
                             (c.ApprovalRequest, {"command_message_id": ids()[0], "decision": "pending"}),
                             (c.Result, {"estado": "accepted"}), (c.Event, {"event_type": "ping"})):
            expected = {c.CommandRequest: c.TipoMensaje.COMMAND_REQUEST,
                        c.ApprovalRequest: c.TipoMensaje.APPROVAL_REQUEST,
                        c.Result: c.TipoMensaje.RESULT, c.Event: c.TipoMensaje.EVENT}[cls]
            self.assertEqual(msg(cls, d, s, payload).kind, expected)

    def test_seis_dispositivos_y_autoridad_unica(self):
        reg = c.RegistroDispositivos()
        for tipo in c.TipoDispositivo:
            d = c.RegistroDispositivo(str(uuid4()), tipo)
            reg.registrar(d)
        with self.assertRaises(ValueError):
            reg.registrar(c.RegistroDispositivo(str(uuid4()), c.TipoDispositivo.PC_NUCLEO))
        with self.assertRaises(ValueError):
            c.RegistroDispositivo(str(uuid4()), c.TipoDispositivo.TABLET_HUD, ("memoria_central",))

    def test_scopes_expiracion_revocacion_y_aislamiento(self):
        r = c.RegistroDispositivos(); now = 1000
        d1 = c.RegistroDispositivo(str(uuid4()), c.TipoDispositivo.PC_NUCLEO)
        d2 = c.RegistroDispositivo(str(uuid4()), c.TipoDispositivo.TABLET_HUD)
        r.registrar(d1); r.registrar(d2)
        s1 = r.crear_sesion(d1.device_id, [c.Scope.STATE_READ], 20, now)
        s2 = r.crear_sesion(d2.device_id, [c.Scope.SENSOR_SUBMIT], 20, now)
        self.assertFalse(r.autorizar(d1.device_id, s1.session_id, c.Scope.UI_CONTROL, now+1))
        self.assertFalse(r.autorizar(d1.device_id, s2.session_id, c.Scope.STATE_READ, now+1))
        self.assertFalse(r.autorizar(d1.device_id, s1.session_id, c.Scope.STATE_READ, now+20))
        self.assertFalse(r.latido(d1.device_id, s1.session_id, now+20))
        s3 = r.crear_sesion(d2.device_id, [c.Scope.STATE_READ], 30, now)
        self.assertTrue(r.revocar_sesion(s3.session_id))
        self.assertFalse(r.autorizar(d2.device_id, s3.session_id, c.Scope.STATE_READ, now+1))
        s4 = r.crear_sesion(d2.device_id, [c.Scope.STATE_READ], 30, now)
        self.assertTrue(r.revocar_dispositivo(d2.device_id))
        self.assertFalse(r.autorizar(d2.device_id, s4.session_id, c.Scope.STATE_READ, now+1))

    def test_observacion_solicitud_y_aprobacion_separadas(self):
        r = c.RegistroDispositivos(); now = 2000
        core = c.RegistroDispositivo(str(uuid4()), c.TipoDispositivo.PC_NUCLEO)
        client = c.RegistroDispositivo(str(uuid4()), c.TipoDispositivo.TABLET_HUD)
        approver = c.RegistroDispositivo(str(uuid4()), c.TipoDispositivo.TELEFONO_MOVIL)
        for d in (core, client, approver): r.registrar(d)
        cs = r.crear_sesion(client.device_id, [c.Scope.OPERATION_REQUEST], 60, now)
        ap = r.crear_sesion(approver.device_id, [c.Scope.OPERATION_APPROVE], 60, now)
        cmd = msg(c.CommandRequest, client.device_id, cs.session_id,
                  {"operacion": "borrar", "sensible": True})
        self.assertFalse(r.autorizar_operacion(cmd, ahora=now+1))
        ok = msg(c.ApprovalRequest, approver.device_id, ap.session_id,
                 {"command_message_id": cmd.message_id, "decision": "approved"})
        self.assertTrue(r.autorizar_operacion(cmd, ok, now+1))
        self.assertFalse(r.autorizar_operacion(cmd, ok, now+60))
        with self.assertRaises(ValueError): msg(c.Observation, client.device_id, cs.session_id,
                                               {"accion": "borrar"})

    def test_secretos_se_sanean_en_payload_url_y_log(self):
        d, s, _, _ = ids()
        event = msg(c.Event, d, s, {"event_type": "diagnostic", "token": "secret-value", "nota": "Bearer abcdefghi",
            "url": "https://host.test/path?token=secret-value&x=1", "texto": "sk-1234567890abcdef"})
        rendered = event.a_json_seguro() + repr(event.payload)
        for secret in ("secret-value", "abcdefghi", "sk-1234567890abcdef", "?token="):
            self.assertNotIn(secret, rendered)
        self.assertIn("[REDACTADO]", rendered)

    def test_imports_api_publica_y_limites_de_payload(self):
        d, s, _, _ = ids()
        self.assertIs(c.Observation, __import__("ecosistema_contratos").Observation)
        with self.assertRaises(ValueError): msg(c.Event, d, s, {"event_type": "x", "items": list(range(129))})
        with self.assertRaises(ValueError): msg(c.Event, d, s, {"event_type": "x", "n": float("inf")})


if __name__ == "__main__":
    unittest.main()
