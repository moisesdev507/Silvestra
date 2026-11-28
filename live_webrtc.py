"""Puente de audio WebRTC (Edge/Chromium) para Gemini Live sin ruido ni bloqueos PortAudio."""
from __future__ import annotations

import asyncio
import http.server
import json
import os
import queue
import socket
import socketserver
import subprocess
import threading
import time
from typing import Callable, Optional
import websockets

import webrtc_ventana as wv

SENAL_SLEEP = b"__WEBRTC_SLEEP__"
HTML_PUENTE = wv.HTML_PUENTE


def buscar_navegador_webrtc() -> Optional[str]:
    cands = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    return next((r for r in cands if r and os.path.isfile(r)), None)


def webrtc_disponible() -> bool:
    return buscar_navegador_webrtc() is not None


def _puerto_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _HTTPReutilizable(socketserver.TCPServer):
    allow_reuse_address = True


class PuenteWebRTC:
    """Gestiona el proceso navegador oculto y las colas PCM bidireccionales."""

    def __init__(
        self,
        on_estado: Optional[Callable[[str], None]] = None,
        on_nivel: Optional[Callable[[float], None]] = None,
    ):
        self.on_estado = on_estado
        self.on_nivel = on_nivel
        self.cola_entrada: queue.Queue = queue.Queue(maxsize=600)
        self.cola_salida: queue.Queue = queue.Queue()
        self.activo = False
        self.dormida = False
        self._ultimo_habla = time.time()
        self._ultimo_estado: Optional[str] = None
        self._t_desconexion_ws: Optional[float] = None
        self._t_ultimo_reintento_nav = 0.0
        self._reintentos_nav = 0
        self._httpd = None
        self._proc = None
        self._loop = None
        self._ws_cliente = None
        self._hilo_ws = None
        self._navegador = None
        self._perfil = ""
        self._url = ""

    def _emitir_estado(self, est: str):
        est_limpio = str(est or "").strip().lower()
        if not est_limpio:
            return
        self.dormida = (est_limpio == "reposo")
        if est_limpio == "escuchando":
            self._ultimo_habla = time.time()
        if est_limpio == self._ultimo_estado:
            return
        self._ultimo_estado = est_limpio
        try:
            import puente_subjetividad
            p = puente_subjetividad.obtener_puente()
            if est_limpio == "reposo":
                p.al_entrar_reposo()
            elif est_limpio in ("escuchando", "hablando"):
                p.al_despertar_o_hablar()
        except Exception:
            pass
        if callable(self.on_estado):
            try:
                self.on_estado(est_limpio)
            except Exception:
                pass

    def _emitir_nivel(self, niv: float):
        if niv > 0.05:
            self._ultimo_habla = time.time()
        if callable(self.on_nivel):
            try:
                self.on_nivel(niv)
            except Exception:
                pass

    def _encolar_entrada(self, item: bytes):
        if self.cola_entrada.full():
            try:
                self.cola_entrada.get_nowait()
            except queue.Empty:
                pass
        try:
            self.cola_entrada.put_nowait(item)
        except queue.Full:
            pass

    def _lanzar_navegador(self) -> bool:
        if not self._navegador:
            return False
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self._proc = subprocess.Popen(
                wv.comando_edge(self._navegador, self._perfil, self._url),
                creationflags=flags,
                startupinfo=wv.startupinfo_oculto(),
            )
            threading.Thread(
                target=wv.ocultar_ventana_pid, args=(self._proc.pid,), daemon=True
            ).start()
            return True
        except Exception as e:
            print(f"[LIVE][WEBRTC] Error lanzando navegador: {e}", flush=True)
            return False

    def iniciar(self) -> bool:
        navegador = buscar_navegador_webrtc()
        if not navegador:
            return False
        self.activo = True
        self._navegador = navegador
        p_http = _puerto_libre()
        p_ws = _puerto_libre()

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(HTML_PUENTE.encode("utf-8"))

            def log_message(self, *a):
                pass

        self._httpd = _HTTPReutilizable(("127.0.0.1", p_http), _Handler)
        threading.Thread(target=self._httpd.serve_forever, daemon=True, name="webrtc-http").start()

        def _correr_ws():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            async def _handler_ws(ws):
                self._ws_cliente = ws
                self._t_desconexion_ws = None
                self._reintentos_nav = 0
                print("[LIVE][WEBRTC] Puente de audio limpio conectado (16kHz).", flush=True)
                self.activar_escucha()

                async def _vigilante():
                    while self.activo:
                        await asyncio.sleep(0.5)
                        ahora = time.time()
                        if not self.dormida and (ahora - self._ultimo_habla > 9.8):
                            self.dormida = True
                            print("[LIVE][WEBRTC] 9s en silencio -> Reposo Azul (0 tokens).", flush=True)
                            self._encolar_entrada(SENAL_SLEEP)
                            self._emitir_estado("reposo")
                            try:
                                if self._ws_cliente is not None:
                                    await self._ws_cliente.send(json.dumps({"type": "reposo"}))
                            except Exception:
                                pass
                        if self._ws_cliente is None:
                            if self._t_desconexion_ws is None:
                                self._t_desconexion_ws = ahora
                            elif ahora - self._t_desconexion_ws > 20.0:
                                if (self._reintentos_nav < 2) and (ahora - self._t_ultimo_reintento_nav >= 30.0):
                                    self._t_ultimo_reintento_nav = ahora
                                    self._reintentos_nav += 1
                                    print(f"[LIVE][WEBRTC] WebSocket sin respuesta >20s. Reintento navegador {self._reintentos_nav}/2...", flush=True)
                                    self._lanzar_navegador()
                        else:
                            self._t_desconexion_ws = None
                            self._reintentos_nav = 0

                t_vigilante = asyncio.create_task(_vigilante())
                async def _salida():
                    while self.activo:
                        try:
                            item = await asyncio.to_thread(self.cola_salida.get, timeout=0.08)
                            if item:
                                await ws.send(item)
                        except queue.Empty:
                            continue
                        except Exception:
                            break

                t_out = asyncio.create_task(_salida())
                try:
                    async for msg in ws:
                        if not self.activo:
                            break
                        if isinstance(msg, bytes):
                            self._encolar_entrada(msg)
                        else:
                            data = json.loads(msg)
                            tipo = data.get("type")
                            if tipo == "estado":
                                self._emitir_estado(str(data.get("v", "escuchando")))
                            elif tipo == "nivel":
                                self._emitir_nivel(float(data.get("v", 0.0)))
                            elif tipo == "interrupted":
                                self.interrumpir_salida()
                            elif tipo == "wake":
                                if self.dormida:
                                    self.dormida = False
                                    print("[LIVE][WEBRTC] Voz detectada -> Despertando a Amarillo.", flush=True)
                                self._ultimo_habla = time.time()
                                self._emitir_estado("escuchando")
                            elif tipo == "sleep":
                                if not self.dormida:
                                    self.dormida = True
                                    print("[LIVE][WEBRTC] 9s en silencio -> Reposo Azul (0 tokens).", flush=True)
                                    self._encolar_entrada(SENAL_SLEEP)
                                    self._emitir_estado("reposo")
                except websockets.ConnectionClosed:
                    pass
                finally:
                    t_vigilante.cancel()
                    t_out.cancel()
                    if self._ws_cliente is ws:
                        self._ws_cliente = None

            async def _main_ws():
                async with websockets.serve(_handler_ws, "127.0.0.1", p_ws):
                    while self.activo:
                        await asyncio.sleep(0.15)

            try:
                self._loop.run_until_complete(_main_ws())
            except Exception:
                pass
            finally:
                try:
                    self._loop.close()
                except Exception:
                    pass

        self._hilo_ws = threading.Thread(target=_correr_ws, daemon=True, name="webrtc-ws")
        self._hilo_ws.start()

        self._perfil = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".kaya_webrtc_perfil")
        wv.preparar_perfil(self._perfil)
        self._url = f"http://127.0.0.1:{p_http}/#{p_ws}"
        if not self._lanzar_navegador():
            self.detener()
            return False
        return True

    def enviar_audio_salida(self, pcm24k: bytes):
        if self.activo and pcm24k:
            self._ultimo_habla = time.time()
            self.cola_salida.put(pcm24k)

    def interrumpir_salida(self):
        if not self.activo:
            return
        with self.cola_salida.mutex:
            self.cola_salida.queue.clear()
        self.cola_salida.put(json.dumps({"type": "interrupted"}))

    def activar_escucha(self):
        self.dormida = False
        self._ultimo_habla = time.time()
        self._emitir_estado("escuchando")
        if self.activo:
            self.cola_salida.put(json.dumps({"type": "escuchando"}))

    def despertar(self):
        self.activar_escucha()

    def despertar_suave(self, frase: str = ""):
        self.activar_escucha()

    def detener(self):
        self.activo = False
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None
