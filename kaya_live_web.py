"""Servidor Web/PWA asíncrono para Kaya Live con WebSocket bidireccional.

Sirve el frontend en web_kaya/ en 0.0.0.0:8765 y permite interactuar con Kaya
desde PC (con cancelación de eco del navegador sin audífonos), Tablet y Celular.
"""
import argparse
import asyncio
import base64
import json
import os
import sys
import threading
from aiohttp import web

import kaya_live_nucleo

RUTA_WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_kaya")
HOST_DEFECTO = "0.0.0.0"
PUERTO_DEFECTO = 8765


class ServidorKayaLiveWeb:
    """Gestiona el servidor aiohttp, conexiones WebSocket y la sesión Live."""

    def __init__(
        self,
        host: str = HOST_DEFECTO,
        puerto: int = PUERTO_DEFECTO,
        modelo: str = kaya_live_nucleo.MODELO_DEFECTO,
        voz: str = kaya_live_nucleo.VOZ_DEFECTO,
    ):
        self.host = host
        self.puerto = puerto
        self.modelo = modelo
        self.voz = voz

        self.app = web.Application()
        self.sesion: Optional[kaya_live_nucleo.SesionKayaLive] = None
        self.ws_actuales = set()
        self.runner = None
        self.site = None
        self._loop_live = None
        self._hilo_live = None

        self._configurar_rutas()

    def _configurar_rutas(self):
        self.app.router.add_get("/", self._handle_index)
        self.app.router.add_get("/ws/live", self._handle_ws)
        if os.path.exists(RUTA_WEB):
            self.app.router.add_static("/", RUTA_WEB)

    async def _handle_index(self, request):
        ruta_index = os.path.join(RUTA_WEB, "index.html")
        if os.path.exists(ruta_index):
            return web.FileResponse(ruta_index)
        return web.Response(text="Kaya Live Web - Frontend no encontrado", status=404)

    def _broadcast_json(self, dato: dict):
        if not self.ws_actuales:
            return
        txt = json.dumps(dato)
        for ws in list(self.ws_actuales):
            if not ws.closed:
                asyncio.run_coroutine_threadsafe(ws.send_str(txt), self.app.loop)

    def _broadcast_audio_bytes(self, trozo: bytes):
        if not self.ws_actuales:
            return
        for ws in list(self.ws_actuales):
            if not ws.closed:
                asyncio.run_coroutine_threadsafe(ws.send_bytes(trozo), self.app.loop)

    def _iniciar_sesion_live_remota(self):
        if self.sesion is not None and not self.sesion._evento_parada.is_set():
            return

        def on_estado(e):
            self._broadcast_json({"tipo": "estado", "estado": e})

        def on_nivel(n):
            self._broadcast_json({"tipo": "nivel", "nivel": n})

        def on_transcripcion(r, t):
            self._broadcast_json({"tipo": "texto", "rol": r, "texto": t})

        def on_audio_salida(b):
            self._broadcast_audio_bytes(b)

        self.sesion = kaya_live_nucleo.SesionKayaLive(
            modelo=self.modelo,
            voz=self.voz,
            saludar_al_iniciar=True,
            audio_local=False,
            on_estado=on_estado,
            on_nivel_voz=on_nivel,
            on_transcripcion=on_transcripcion,
            on_audio_salida=on_audio_salida,
        )

        def _hilo_async():
            self._loop_live = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop_live)
            try:
                self._loop_live.run_until_complete(self.sesion.ejecutar())
            except Exception as e:
                print(f"[LIVE Web] Sesión Live terminada: {e}", flush=True)

        self._hilo_live = threading.Thread(target=_hilo_async, name="kaya-live-web-sesion", daemon=True)
        self._hilo_live.start()

    async def _handle_ws(self, request):
        ws = web.WebSocketResponse(heartbeat=15.0)
        await ws.prepare(request)
        self.ws_actuales.add(ws)
        print(f"[LIVE Web] Cliente conectado desde {request.remote}", flush=True)

        self._iniciar_sesion_live_remota()

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.BINARY:
                    if self.sesion:
                        self.sesion.inyectar_audio_pcm16(msg.data)
                elif msg.type == web.WSMsgType.TEXT:
                    try:
                        cmd = json.loads(msg.data)
                        t = cmd.get("tipo")
                        if t == "imagen" and self.sesion:
                            b64 = cmd.get("jpeg", "")
                            if b64:
                                raw_jpeg = base64.b64decode(b64)
                                asyncio.run_coroutine_threadsafe(
                                    self.sesion.enviar_imagen_jpeg(raw_jpeg),
                                    self._loop_live or self.app.loop
                                )
                        elif t == "toggle" and self.sesion:
                            if self.sesion._pausado:
                                self.sesion.reanudar()
                            else:
                                self.sesion.pausar()
                    except Exception as e:
                        print(f"[LIVE Web] Error procesando JSON WS: {e}", flush=True)
                elif msg.type == web.WSMsgType.ERROR:
                    print(f"[LIVE Web] Excepción WS: {ws.exception()}", flush=True)
        finally:
            self.ws_actuales.discard(ws)
            print(f"[LIVE Web] Cliente desconectado de {request.remote}", flush=True)
            if not self.ws_actuales and self.sesion:
                self.sesion.pausar()
        return ws

    async def iniciar_servidor(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.puerto)
        await self.site.start()
        print(f"[LIVE Web] Servidor Kaya Live Web escuchando en http://{self.host}:{self.puerto}", flush=True)

    async def detener_servidor(self):
        if self.sesion:
            self.sesion.detener()
        if self.runner:
            await self.runner.cleanup()


def verificar_web() -> bool:
    """Valida carga del servidor y existencia de la suite web sin bloqueo."""
    archivos_requeridos = ["index.html", "app.js", "styles.css", "manifest.json"]
    for arch in archivos_requeridos:
        ruta = os.path.join(RUTA_WEB, arch)
        if not os.path.exists(ruta):
            print(f"[LIVE Web Verify] Falta archivo estático: {arch}")
            return False
    srv = ServidorKayaLiveWeb(puerto=9999)
    print(f"[LIVE Web Verify] Servidor instanciado correctamente con {len(srv.app.router.routes())} rutas.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Servidor Web/PWA para Kaya Live.")
    parser.add_argument("--host", default=HOST_DEFECTO)
    parser.add_argument("--puerto", type=int, default=PUERTO_DEFECTO)
    parser.add_argument("--modelo", default=kaya_live_nucleo.MODELO_DEFECTO)
    parser.add_argument("--voz", default=kaya_live_nucleo.VOZ_DEFECTO)
    parser.add_argument("--verificar", action="store_true", help="Valida rutas y estáticos sin iniciar bucle")
    args = parser.parse_args()

    if args.verificar:
        ok = verificar_web()
        sys.exit(0 if ok else 1)

    servidor = ServidorKayaLiveWeb(host=args.host, puerto=args.puerto, modelo=args.modelo, voz=args.voz)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(servidor.iniciar_servidor())
        loop.run_forever()
    except KeyboardInterrupt:
        print("\n[LIVE Web] Apagando servidor...", flush=True)
        loop.run_until_complete(servidor.detener_servidor())


if __name__ == "__main__":
    main()
