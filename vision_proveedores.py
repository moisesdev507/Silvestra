"""Adaptadores remoto/local y offline OCR para modelos de vision."""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Any, Optional


def redactar_error(texto: str) -> str:
    limpio = str(texto or "")
    limpio = re.sub(r"(?i)authorization\s*:.*$", "Authorization: ***", limpio)
    limpio = re.sub(r"(?i)(authorization|api[_-]?key|token|clave)\s*[:=]\s*\S+", "***", limpio)
    limpio = re.sub(r"(?i)bearer\s+[A-Za-z0-9._-]+", "Bearer ***", limpio)
    limpio = re.sub(r"[A-Za-z0-9]{32,}", "***", limpio)
    return limpio[:500]


class AdaptadorProveedorVision:
    def comprender(
        self,
        pregunta: str,
        ruta_imagen: str,
        contexto_breve: str = "",
        timeout_seg: float = 20.0,
    ) -> dict:
        raise NotImplementedError


class ProveedorVisionRemoto(AdaptadorProveedorVision):
    def __init__(self, url: str, api_key: str, modelo: str,
                 timeout_seg: float = 20.0) -> None:
        self.url = str(url or "")
        self.api_key = str(api_key or "")
        self.modelo = str(modelo or "")
        self.timeout_seg = float(timeout_seg)

    def comprender(
        self,
        pregunta: str,
        ruta_imagen: str,
        contexto_breve: str = "",
        autorizacion_externa: bool = False,
        timeout_seg: Optional[float] = None,
    ) -> dict:
        if not autorizacion_externa:
            return {"error": "ENVIO_EXTERNO_NO_AUTORIZADO"}
        if not self.api_key:
            return {"error": "API_KEY_NO_CONFIGURADA"}
        if not self.url:
            return {"error": "PROVEEDOR_REMOTO_SIN_URL"}
        import base64
        import os
        if not os.path.isfile(ruta_imagen):
            return {"error": "IMAGEN_INEXISTENTE"}
        with open(ruta_imagen, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        payload = {
            "model": self.modelo,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": str(pregunta or contexto_breve or "Describe esta imagen")},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
                ],
            }],
            "max_tokens": 600,
        }
        datos = json.dumps(payload).encode("utf-8")
        solicitud = urllib.request.Request(
            self.url,
            data=datos,
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            timeout = float(timeout_seg or self.timeout_seg)
            with urllib.request.urlopen(solicitud, timeout=timeout) as resp:
                crudo = resp.read().decode("utf-8", errors="replace")
            objeto = json.loads(crudo)
            contenido = (
                objeto.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            if not isinstance(contenido, str):
                contenido = ""
            return {"descripcion": contenido, "confianza": None}
        except Exception as exc:
            return {"error": redactar_error(str(exc))}


class ProveedorVisionLocal(AdaptadorProveedorVision):
    def __init__(self, url: str = "http://127.0.0.1:11434/api/generate",
                 modelo: str = "llava", timeout_seg: float = 20.0) -> None:
        self.url = str(url)
        self.modelo = str(modelo)
        self.timeout_seg = float(timeout_seg)

    def comprender(
        self,
        pregunta: str,
        ruta_imagen: str,
        contexto_breve: str = "",
        timeout_seg: Optional[float] = None,
    ) -> dict:
        import base64
        import os
        if not os.path.isfile(ruta_imagen):
            return {"error": "IMAGEN_INEXISTENTE"}
        with open(ruta_imagen, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        payload = {
            "model": self.modelo,
            "prompt": str(pregunta or contexto_breve or "Describe esta imagen"),
            "images": [b64],
            "stream": False,
        }
        solicitud = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                solicitud, timeout=float(timeout_seg or self.timeout_seg)
            ) as resp:
                obj = json.loads(resp.read().decode("utf-8", errors="replace"))
            return {"descripcion": str(obj.get("response", "")), "confianza": None}
        except Exception as exc:
            return {"error": redactar_error(str(exc))}


class ProveedorVisionSoloLocalOCR(AdaptadorProveedorVision):
    def __init__(self, motor_ocr=None) -> None:
        self.motor_ocr = motor_ocr

    def comprender(
        self,
        pregunta: str,
        ruta_imagen: str,
        contexto_breve: str = "",
        timeout_seg: Optional[float] = None,
    ) -> dict:
        if self.motor_ocr is None:
            return {
                "descripcion": "",
                "texto_extraido": "",
                "bloques_ocr": [],
                "limitaciones": ["OCR local no disponible"],
                "confianza": None,
            }
        bloques, limitaciones = self.motor_ocr.extraer(ruta_imagen)
        texto = "\n".join(str(b.texto) for b in bloques if str(b.texto).strip())
        return {
            "descripcion": "Resultado OCR local",
            "texto_extraido": texto,
            "bloques_ocr": bloques,
            "limitaciones": limitaciones,
            "confianza": None,
        }
