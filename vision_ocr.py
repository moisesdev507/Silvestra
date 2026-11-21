"""OCR desacoplado con extractores locales o registrados."""
from __future__ import annotations

from typing import Callable, Optional

from vision_modelo import BloqueTextoOCR


class ErrorOCR(ValueError):
    pass


class MotorOCR:
    def __init__(self) -> None:
        self._extractor: Optional[Callable[..., list[BloqueTextoOCR]]] = None

    def registrar_extractor(
        self,
        extractor: Callable[..., list[BloqueTextoOCR]],
        sobrescribir: bool = True,
    ) -> bool:
        if not callable(extractor):
            raise TypeError("Extractor OCR invalido")
        if self._extractor is not None and not sobrescribir:
            return False
        self._extractor = extractor
        return True

    def disponible(self) -> bool:
        return self._extractor is not None

    def extraer(self, ruta: str, idioma: str = "spa") -> tuple[list[BloqueTextoOCR], list[str]]:
        if self._extractor is None:
            return [], ["OCR local no disponible"]
        try:
            bloques = self._extractor(ruta, idioma)
            normalizados = []
            for bloque in bloques:
                if isinstance(bloque, BloqueTextoOCR):
                    normalizados.append(bloque)
                elif isinstance(bloque, dict):
                    normalizados.append(BloqueTextoOCR(
                        texto=str(bloque.get("texto", "")),
                        region=bloque.get("region"),
                        idioma=str(bloque.get("idioma", idioma)),
                        origen_ocr=str(bloque.get("origen_ocr", "local")),
                    ))
            return normalizados, []
        except Exception:
            return [], ["OCR local fallo"]


def unir_texto(bloques: list[BloqueTextoOCR]) -> str:
    lineas = []
    for bloque in bloques:
        texto = str(bloque.texto or "").strip()
        if texto:
            lineas.append(texto)
    return "\n".join(lineas)
