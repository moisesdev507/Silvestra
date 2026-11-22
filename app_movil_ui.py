"""Manejador y despachador de la interfaz web PWA móvil para Lyris."""
from __future__ import annotations

import json
from typing import Any

from app_movil_html import PAGINA_MOVIL_HTML

# Icono vectorizado SVG para el manifest PWA
ICONO_LYRIS_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">'
    '<circle cx="64" cy="64" r="60" fill="#0a0d14" stroke="#38bdf8" stroke-width="4"/>'
    '<circle cx="64" cy="64" r="48" fill="none" stroke="#0ea5e9" stroke-width="1.5" stroke-dasharray="4 4"/>'
    '<ellipse cx="44" cy="54" rx="8" ry="12" fill="#38bdf8"/>'
    '<ellipse cx="84" cy="54" rx="8" ry="12" fill="#38bdf8"/>'
    '<path d="M48 80 Q64 96 80 80" fill="none" stroke="#38bdf8" stroke-width="4" stroke-linecap="round"/>'
    '</svg>'
)

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
            "src": f"data:image/svg+xml;utf8,{ICONO_LYRIS_SVG}",
            "sizes": "192x192 512x512",
            "type": "image/svg+xml",
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
    """Atiende rutas web PWA para el cliente móvil: /movil, /manifest.json, /sw.js."""
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

    return False
