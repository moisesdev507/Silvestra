"""Manejador y despachador de la interfaz web PWA móvil para Lyris."""
from __future__ import annotations

import io
import ipaddress
import json
import os
import socketserver
import http.server
import threading
from typing import Any, Dict

from PIL import Image, ImageDraw

from app_movil_html import PAGINA_MOVIL_HTML

_bloqueo = threading.RLock()
_cache_iconos: Dict[int, bytes] = {}
_servidor_8766 = None
_RED_TAILSCALE = ipaddress.ip_network("100.64.0.0/10")

PAGINA_INSTALAR_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>Instalar Lyris</title>
<style>
body{font-family:sans-serif;background:#0a0d14;color:#f3f4f6;padding:20px;text-align:center;margin:0;}
.card{background:#111827;border:1px solid #1f2937;border-radius:18px;padding:22px 18px;max-width:380px;margin:20px auto;}
h1{font-size:19px;color:#38bdf8;margin-bottom:10px;}
p{font-size:13.5px;color:#9ca3af;line-height:1.45;margin-bottom:16px;}
.btn{display:block;background:#38bdf8;color:#0a0d14;padding:12px;border-radius:24px;text-decoration:none;font-weight:700;margin-bottom:10px;}
.btn-sec{background:#1f2937;color:#38bdf8;border:1px solid #374151;}
.steps{text-align:left;font-size:12.5px;color:#cbd5e1;background:#0f172a;padding:12px;border-radius:12px;margin:14px 0;}
.steps ol{margin:0;padding-left:18px;}
.steps li{margin-bottom:6px;}
</style>
</head>
<body>
<div class="card">
<h1>📲 Instalar Lyris en tu Celular</h1>
<p>Para instalar Lyris con ícono nativo y sin avisos de certificado en tu red local o Tailscale:</p>
<a href="http://{HOST}:8766/movil?token={TOKEN}" class="btn">🚀 Abrir en HTTP Local (Puerto 8766)</a>
<div class="steps">
<strong>Pasos para agregar ícono PWA:</strong>
<ol>
<li>Toca el botón azul superior para entrar en HTTP local.</li>
<li>En Chrome, toca el menú de 3 puntos (⋮).</li>
<li>Selecciona <strong>"Instalar aplicación"</strong> o <strong>"Agregar a pantalla principal"</strong>.</li>
</ol>
</div>
<a href="/movil" class="btn btn-sec">⬅️ Volver a Lyris Central</a>
</div>
</body>
</html>
"""


def _es_ip_permitida(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_loopback or ip.is_private or ip in _RED_TAILSCALE
    except Exception:
        return False


class HandlerAuxiliar8766(http.server.BaseHTTPRequestHandler):
    """Atiende peticiones en el puerto local 8766 para instalación sin barreras de certificado."""

    def do_GET(self):
        if not _es_ip_permitida(self.client_address[0]):
            self.send_response(403)
            self.end_headers()
            return
        p = self.path.split("?", 1)[0]
        if p in ("/movil", "/movil/", "/movil/instalar", "/manifest.json", "/sw.js") or p.startswith("/icon-") or "cert" in p:
            if despachar_get_movil(self, p):
                return
        self.send_response(302)
        self.send_header("Location", "/movil")
        self.end_headers()

    def log_message(self, format, *args):
        pass


def iniciar_servidor_auxiliar_8766(puerto: int = 8766):
    """Inicia el servidor HTTP auxiliar en segundo plano si no está corriendo."""
    global _servidor_8766
    with _bloqueo:
        if _servidor_8766 is not None:
            return
        try:
            class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
                daemon_threads = True

            srv = ThreadingServer(("0.0.0.0", puerto), HandlerAuxiliar8766)
            th = threading.Thread(target=srv.serve_forever, daemon=True, name="LyrisHTTP8766")
            th.start()
            _servidor_8766 = srv
        except Exception:
            pass


def generar_icono_png(tam: int = 192) -> bytes:
    """Genera en memoria un ícono PNG con el emblema holográfico de Lyris."""
    with _bloqueo:
        if tam in _cache_iconos:
            return _cache_iconos[tam]

        img = Image.new("RGBA", (tam, tam), (10, 13, 20, 255))
        draw = ImageDraw.Draw(img)

        ancho_borde = max(2, tam // 36)
        draw.ellipse((4, 4, tam - 5, tam - 5), outline=(56, 189, 248, 255), width=ancho_borde)

        pad = tam // 6
        draw.ellipse((pad, pad, tam - pad, tam - pad), outline=(14, 165, 233, 180), width=max(1, tam // 64))

        ey_w, ey_h = max(3, tam // 12), max(5, tam // 8)
        cx1, cx2 = int(tam * 0.36), int(tam * 0.64)
        cy = int(tam * 0.46)
        draw.ellipse((cx1 - ey_w, cy - ey_h, cx1 + ey_w, cy + ey_h), fill=(56, 189, 248, 255))
        draw.ellipse((cx2 - ey_w, cy - ey_h, cx2 + ey_w, cy + ey_h), fill=(56, 189, 248, 255))

        m_pad = int(tam * 0.32)
        draw.arc((m_pad, int(tam * 0.42), tam - m_pad, int(tam * 0.74)), start=25, end=155, fill=(56, 189, 248, 255), width=ancho_borde)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        _cache_iconos[tam] = png_bytes
        return png_bytes


MANIFEST_JSON = json.dumps({
    "name": "Lyris - Asistente Personal",
    "short_name": "Lyris",
    "description": "Asistente inteligente personal modular con voz y mente unificada.",
    "start_url": "/movil",
    "display": "standalone",
    "background_color": "#0a0d14",
    "theme_color": "#0a0d14",
    "icons": [
        {
            "src": "/icon-192.png",
            "sizes": "192x192",
            "type": "image/png",
            "purpose": "any maskable"
        },
        {
            "src": "/icon-512.png",
            "sizes": "512x512",
            "type": "image/png",
            "purpose": "any maskable"
        }
    ]
}, ensure_ascii=False, indent=2)

SW_JS = """// Service Worker para PWA Lyris
const CACHE_NAME = 'lyris-pwa-v1';
self.addEventListener('install', (e) => { self.skipWaiting(); });
self.addEventListener('activate', (e) => { e.waitUntil(clients.claim()); });
self.addEventListener('fetch', (e) => {
  if (e.request.method === 'GET' && e.request.url.includes('/movil')) {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
  }
});
"""


def despachar_get_movil(handler: Any, path: str) -> bool:
    """Atiende rutas web PWA para el cliente móvil: /movil, /manifest.json, /sw.js, /icon-*.png."""
    iniciar_servidor_auxiliar_8766()
    p = path.split("?", 1)[0].rstrip("/")

    if p in ("/movil", ""):
        btn_app = '<a href="/movil/instalar" class="btn-badge" style="text-decoration:none;" title="Instalar App">📲 App</a>'
        html_inyectado = PAGINA_MOVIL_HTML.replace("📜 Cert</a>", f"📜 Cert</a>\n    {btn_app}")
        raw = html_inyectado.encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(raw)))
        handler.send_header("Cache-Control", "no-cache")
        handler.end_headers()
        try:
            handler.wfile.write(raw)
        except OSError:
            pass
        return True

    if p == "/movil/instalar":
        host_h = handler.headers.get("Host", "127.0.0.1") if hasattr(handler, "headers") and handler.headers else "127.0.0.1"
        host_req = str(host_h).split(":")[0] if host_h else "127.0.0.1"
        tok = getattr(handler, "token_sesion", None)
        if not tok or not isinstance(tok, str):
            tok = "tablet_hud_owner"
        html = PAGINA_INSTALAR_HTML.replace("{HOST}", host_req).replace("{TOKEN}", tok)
        raw = html.encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        try:
            handler.wfile.write(raw)
        except OSError:
            pass
        return True

    if p in ("/movil/lyris.apk", "/lyris.apk"):
        apk_path = "Lyris.apk"
        if os.path.exists(apk_path):
            with open(apk_path, "rb") as f:
                raw_apk = f.read()
            handler.send_response(200)
            handler.send_header("Content-Type", "application/vnd.android.package-archive")
            handler.send_header("Content-Disposition", 'attachment; filename="Lyris.apk"')
            handler.send_header("Content-Length", str(len(raw_apk)))
            handler.end_headers()
            try:
                handler.wfile.write(raw_apk)
            except OSError:
                pass
            return True
        else:
            handler.send_response(302)
            handler.send_header("Location", "/movil/instalar")
            handler.end_headers()
            return True

    if p == "/manifest.json":
        raw = MANIFEST_JSON.encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "application/manifest+json; charset=utf-8")
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        try:
            handler.wfile.write(raw)
        except OSError:
            pass
        return True

    if p == "/sw.js":
        raw = SW_JS.encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "application/javascript; charset=utf-8")
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        try:
            handler.wfile.write(raw)
        except OSError:
            pass
        return True

    if p in ("/icon-192.png", "/icon-512.png"):
        tam = 512 if "512" in p else 192
        png_data = generar_icono_png(tam)
        handler.send_response(200)
        handler.send_header("Content-Type", "image/png")
        handler.send_header("Content-Length", str(len(png_data)))
        handler.send_header("Cache-Control", "public, max-age=86400")
        handler.end_headers()
        try:
            handler.wfile.write(png_data)
        except OSError:
            pass
        return True

    if p in ("/movil/cert.pem", "/movil/cert", "/movil/lyris_cert.pem", "/cert.pem", "/lyris_cert.pem", "/api/movil/cert"):
        cert_path = "hud_cert.pem"
        if os.path.exists(cert_path):
            with open(cert_path, "rb") as f:
                raw_cert = f.read()
            handler.send_response(200)
            handler.send_header("Content-Type", "application/x-pem-file")
            handler.send_header("Content-Disposition", 'attachment; filename="lyris_cert.pem"')
            handler.send_header("Content-Length", str(len(raw_cert)))
            handler.end_headers()
            try:
                handler.wfile.write(raw_cert)
            except OSError:
                pass
            return True

    return False
