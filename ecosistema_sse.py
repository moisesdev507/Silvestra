"""Broker SSE en memoria con replay acotado, heartbeat y límites explícitos."""
from collections import deque
from contextlib import contextmanager
from threading import BoundedSemaphore, Condition, RLock
import json, time

from ecosistema_contratos import serializar_seguro


class BusSSE:
    def __init__(self, capacidad=256, max_conexiones=8, max_pet=30, ventana_seg=10):
        if min(capacidad, max_conexiones, max_pet) < 1 or ventana_seg <= 0:
            raise ValueError("límites SSE inválidos")
        self._eventos = deque(maxlen=capacidad)
        self._id = 0
        self._lock = RLock()
        self._cambio = Condition(self._lock)
        self._slots = BoundedSemaphore(max_conexiones)
        self._max_pet, self._ventana = max_pet, float(ventana_seg)
        self._peticiones = {}

    @property
    def ultimo_id(self):
        with self._lock: return self._id

    def publicar(self, payload, tipo="message"):
        data = serializar_seguro(payload)
        with self._cambio:
            self._id += 1
            item = {"id": self._id, "event": str(tipo)[:40], "data": data}
            self._eventos.append(item); self._cambio.notify_all()
            return self._id

    def desde(self, last_event_id=None):
        try: last = max(0, int(last_event_id or 0))
        except (TypeError, ValueError): raise ValueError("Last-Event-ID inválido")
        with self._lock:
            if self._eventos and last < self._eventos[0]["id"] - 1:
                return [{"id": self._id, "event": "reset", "data": "{}"}]
            return [dict(e) for e in self._eventos if e["id"] > last]

    def esperar(self, last_event_id, timeout=15):
        try: last = max(0, int(last_event_id or 0))
        except (TypeError, ValueError): raise ValueError("Last-Event-ID inválido")
        with self._cambio:
            if self._id <= last: self._cambio.wait(max(0.0, float(timeout)))
            return self.desde(last)

    def permitir_peticion(self, clave, ahora=None):
        now = time.monotonic() if ahora is None else float(ahora)
        with self._lock:
            q = self._peticiones.setdefault(str(clave), deque())
            while q and q[0] <= now - self._ventana: q.popleft()
            if len(q) >= self._max_pet: return False
            q.append(now)
            if len(self._peticiones) > 1024:
                self._peticiones = {k: v for k, v in self._peticiones.items() if v}
            return True

    @contextmanager
    def conexion(self):
        if not self._slots.acquire(blocking=False):
            raise ConnectionError("límite de conexiones SSE alcanzado")
        try: yield
        finally: self._slots.release()

    @staticmethod
    def codificar(item):
        return (f"id: {int(item['id'])}\nevent: {item['event']}\ndata: {item['data']}\n\n").encode("utf-8")

    @staticmethod
    def heartbeat(): return b": heartbeat\n\n"

    def servir_http(self, h, detener, bridge, identity=None):
        try: slot = self.conexion(); slot.__enter__()
        except ConnectionError:
            h.send_response(429); h.send_header("Cache-Control", "no-store"); h.end_headers(); return
        try:
            h.send_response(200)
            for k,v in bridge.cors(h.headers.get("Origin", ""),h.headers.get("Host", ""),h.server.tls).items(): h.send_header(k,v)
            h.send_header("Content-Type","text/event-stream; charset=utf-8")
            h.send_header("Cache-Control","no-cache, no-store"); h.send_header("X-Accel-Buffering","no"); h.end_headers()
            last=h.headers.get("Last-Event-ID"); batch=self.desde(last)
            if last is None and batch: batch=batch[-1:]
            for event in batch:
                if event["event"]=="reset":
                    event={"id":event["id"],"event":"state","data":serializar_seguro(getattr(h.server.gestor,"_ultimo_estado",{}))}
                h.wfile.write(self.codificar(event)); h.wfile.flush(); last=str(event["id"])
            while not detener.is_set():
                if identity and not bridge.gestor.autorizar(identity, "state:read"): break
                batch=self.esperar(last,15)
                if not batch: h.wfile.write(self.heartbeat()); h.wfile.flush(); continue
                for event in batch:
                    if event["event"]=="reset":
                        event={"id":event["id"],"event":"state","data":serializar_seguro(getattr(h.server.gestor,"_ultimo_estado",{}))}
                    h.wfile.write(self.codificar(event)); h.wfile.flush(); last=str(event["id"])
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError,OSError,ValueError): pass
        finally: slot.__exit__(None,None,None)
