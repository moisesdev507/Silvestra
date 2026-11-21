"""Historial temporal auditivo limitado a metadatos sanitizados."""
from __future__ import annotations
import re
import threading
import time
from collections import deque
from audio_evento_modelo import EventoAcustico, CategoriaSonido, NivelRelevanciaSonido


def _texto_seguro(texto):
    texto = re.sub(r"(?i)(password|token|secret|clave|api[_-]?key)\s*[:=]\s*\S+", r"\1=***", str(texto or ""))
    return re.sub(r"[\r\n\t]+", " ", texto)[:300]


class ContextoAcusticoTemporal:
    def __init__(self, max_eventos=32, ttl_seg=180.0, contexto_windows=None):
        self._lock = threading.RLock()
        self.ttl = max(1, ttl_seg)
        self.eventos = deque(maxlen=max(1, int(max_eventos)))
        self.contexto_windows = contexto_windows
        self._analisis = {}

    def _purga(self):
        ahora = time.time()
        while self.eventos and ahora - self.eventos[0]["timestamp"] > self.ttl:
            self.eventos.popleft()
        vivos = {e.get("id_evento") for e in self.eventos}
        self._analisis = {k: v for k, v in self._analisis.items() if k in vivos}

    def agregar(self, evento: EventoAcustico, contexto=None):
        with self._lock:
            self._purga()
            cat = evento.clasificacion.categoria.value
            repet = sum(1 for e in self.eventos if e["categoria"] == cat and evento.timestamp-e["timestamp"] <= 8)
            evento.repeticiones_recientes = repet
            if repet >= 2 and cat in ("golpes", "timbre", "ladridos"):
                evento.relevancia = NivelRelevanciaSonido.alta
                evento.observaciones_verificables.append(f"{repet+1} eventos {cat} en 8 s")
            ctx = contexto or {}
            safe = {str(k)[:40]: _texto_seguro(v) for k, v in ctx.items() if isinstance(v, (str, int, float, bool))}
            evento.contexto_windows_asociado = safe
            entry = {"id_evento": evento.id_evento, "timestamp": evento.timestamp, "categoria": cat,
                "energia_rms": float(evento.energia_rms), "ratio_voz_vad": float(evento.ratio_voz_vad),
                "relevancia": evento.relevancia.value,
                "observaciones": [_texto_seguro(x) for x in evento.observaciones_verificables],
                "interpretaciones": [_texto_seguro(x) for x in evento.interpretaciones_inciertas],
                "transcripcion": _texto_seguro(evento.transcripcion_breve), "contexto": safe}
            self.eventos.append(entry)
            self._analisis[evento.id_evento] = entry
            self._purga()
            return evento

    def consultar_contexto_auditivo(self, pregunta: str, id_analisis: str | None = None):
        with self._lock:
            self._purga()
            filas = [self._analisis[id_analisis]] if id_analisis in self._analisis else list(self.eventos)
            if not filas:
                return {"respuesta": "No hay audio analizado recientemente.", "eventos": []}
            cats = [x["categoria"] for x in filas]
            habla = [x["transcripcion"] for x in filas if x["categoria"] == "voz_humana" and x["transcripcion"]]
            rep = {c: cats.count(c) for c in set(cats) if cats.count(c) > 1}
            respuesta = "Se detectó: " + ", ".join(sorted(set(cats))) + "."
            respuesta += " Hubo voz humana." if "voz_humana" in cats else " No se detectó voz humana."
            if rep: respuesta += " Repeticiones: " + ", ".join(f"{k} ({v})" for k,v in rep.items()) + "."
            if habla: respuesta += " Fragmentos de voz: " + " / ".join(habla[:3])
            return {"respuesta": respuesta[:500], "eventos": [dict(x) for x in filas]}
