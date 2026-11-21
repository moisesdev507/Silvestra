"""Modelos normalizados de comprension visual y evidencia."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SolicitudVisual:
    ruta_imagen: str
    modalidad: str = "imagen"
    pregunta: str = ""
    autorizacion_externa: bool = False
    contexto_breve: str = ""
    id_entrada: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if self.modalidad not in ("imagen", "captura_pantalla"):
            raise ValueError("modalidad visual invalida")
        self.ruta_imagen = str(self.ruta_imagen or "")
        self.pregunta = str(self.pregunta or "").strip()
        self.contexto_breve = str(self.contexto_breve or "").strip()
        if not isinstance(self.autorizacion_externa, bool):
            raise TypeError("autorizacion_externa debe ser bool")


@dataclass
class BloqueTextoOCR:
    texto: str
    region: Any = None
    idioma: str = ""
    origen_ocr: str = "simulado"

    def a_dict(self) -> dict:
        return {
            "texto": str(self.texto),
            "region": self.region,
            "idioma": self.idioma,
            "origen_ocr": self.origen_ocr,
        }


@dataclass
class ElementoVisual:
    nombre: str
    categoria: str = "desconocido"
    ubicacion_relativa: Any = None
    verificable: bool = True

    def a_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "categoria": self.categoria,
            "ubicacion_relativa": self.ubicacion_relativa,
            "verificable": bool(self.verificable),
        }


@dataclass
class ResultadoComprensionVisual:
    id_entrada: str
    referencia_imagen: str
    descripcion: str = ""
    elementos_identificados: list[ElementoVisual] = field(default_factory=list)
    texto_extraido: str = ""
    bloques_ocr: list[BloqueTextoOCR] = field(default_factory=list)
    observaciones_verificables: list[str] = field(default_factory=list)
    interpretaciones_inciertas: list[str] = field(default_factory=list)
    nivel_confianza: Optional[float] = None
    limitaciones: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    sugerencia_accion: Optional[dict] = None
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.nivel_confianza is not None:
            try:
                valor = float(self.nivel_confianza)
                if not 0.0 <= valor <= 1.0:
                    self.nivel_confianza = None
                else:
                    self.nivel_confianza = valor
            except (TypeError, ValueError):
                self.nivel_confianza = None

    def a_resumen_cerebro(self, max_caracteres: int = 600) -> str:
        partes = [
            "VISION:",
            self.descripcion,
            "TEXT0_OCR:" if False else "",
        ]
        if self.texto_extraido:
            partes.append("Texto extraido: " + self.texto_extraido)
        if self.observaciones_verificables:
            partes.append("Verificable: " + "; ".join(self.observaciones_verificables))
        if self.interpretaciones_inciertas:
            partes.append("Posible: " + "; ".join(self.interpretaciones_inciertas))
        if self.limitaciones:
            partes.append("Limitaciones: " + "; ".join(self.limitaciones))
        texto = "\n".join(p for p in partes if p)
        limite = max(20, int(max_caracteres))
        return texto[:limite]

    def a_dict(self) -> dict:
        return {
            "id_entrada": self.id_entrada,
            "referencia_imagen": self.referencia_imagen,
            "descripcion": self.descripcion,
            "elementos_identificados": [e.a_dict() for e in self.elementos_identificados],
            "texto_extraido": self.texto_extraido,
            "bloques_ocr": [b.a_dict() for b in self.bloques_ocr],
            "observaciones_verificables": list(self.observaciones_verificables),
            "interpretaciones_inciertas": list(self.interpretaciones_inciertas),
            "nivel_confianza": self.nivel_confianza,
            "limitaciones": list(self.limitaciones),
            "errores": list(self.errores),
            "sugerencia_accion": self.sugerencia_accion,
            "timestamp": self.timestamp,
        }
