"""Manejador y despachador de la interfaz web PWA móvil para Lyris."""
from __future__ import annotations

import io
import json
import threading
from typing import Any, Dict

from PIL import Image, ImageDraw

from app_movil_html import PAGINA_MOVIL_HTML

_bloqueo = threading.RLock()
_cache_iconos: Dict[int, bytes] = {}


def generar_icono_png(tam: int = 192) -> bytes:
    """Genera en memoria un ícono PNG de alta definición con el emblema holográfico de Lyris."""
    with _bloqueo:
        if tam in _cache_iconos:
            return _cache_iconos[tam]

        img = Image.new("RGBA", (tam, tam), (10, 13, 20, 255))
        draw = ImageDraw.Draw(img)

        # Anillo exterior cian
        ancho_borde = max(2, tam // 36)
        draw.ellipse((4, 4, tam - 5, tam - 5), outline=(56, 189, 248, 255), width=ancho_borde)

        # Anillo interno suave
        pad = tam // 6
        draw.ellipse((pad, pad, tam - pad, tam - pad), outline=(14, 165, 233, 180), width=max(1, tam // 64))

        # Ojos holográficos
        ey_w, ey_h = max(3, tam // 12), max(5, tam // 8)
        cx1, cx2 = int(tam * 0.36), int(tam * 0.64)
        cy = int(tam * 0.46)
        draw.ellipse((cx1 - ey_w, cy - ey_h, cx1 + ey_w, cy + ey_h), fill=(56, 189, 248, 255))
        draw.ellipse((cx2 - ey_w, cy - ey_h, cx2 + ey_w, cy + ey_h), fill=(56, 189, 248, 255))

        # Sonrisa sutil
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
    p = path.split("?", 1)[0].rstrip("/")
    if p in ("/movil", ""):
        raw = PAGINA_MOVIL_HTML.encode("utf-8")
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
        import os
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
