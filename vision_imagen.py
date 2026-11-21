"""Validacion segura y normalizacion de imagenes sin bombas de memoria."""
from __future__ import annotations

import os
import tempfile
from typing import Optional

from archivos_seguridad import ConfiguracionSandboxArchivos


class ErrorImagenVisual(ValueError):
    pass


def _firma(ruta: str) -> str:
    with open(ruta, "rb") as f:
        inicio = f.read(16)
    if inicio.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if inicio.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if inicio[:4] == b"RIFF" and inicio[8:12] == b"WEBP":
        return "WebP"
    return ""


def inspeccionar_cabecera(ruta: str) -> tuple[str, int, int]:
    formato = _firma(ruta)
    if formato not in ("PNG", "JPEG", "WebP"):
        raise ErrorImagenVisual("Formato invalido o extension falsificada")
    try:
        from PIL import Image
        with Image.open(ruta) as img:
            img.verify()
        with Image.open(ruta) as img:
            ancho, alto = img.size
    except Exception as exc:
        raise ErrorImagenVisual("Imagen corrupta o truncada") from exc
    if ancho <= 0 or alto <= 0:
        raise ErrorImagenVisual("Dimensiones invalidas")
    return formato, ancho, alto


def validar_y_normalizar(
    ruta: str,
    sandbox: Optional[ConfiguracionSandboxArchivos] = None,
    max_bytes: int = 5 * 1024 * 1024,
    max_ancho: int = 8192,
    max_alto: int = 8192,
    max_megapixeles: float = 32.0,
    max_lado_normalizado: int = 1280,
) -> dict:
    if not isinstance(ruta, str) or not ruta.strip():
        raise ErrorImagenVisual("Ruta inexistente")
    ruta = os.path.abspath(os.path.realpath(ruta))
    if sandbox is not None:
        ruta = sandbox.validar_existente(ruta)
    if not os.path.isfile(ruta):
        raise ErrorImagenVisual("Archivo inexistente")
    tamano = os.path.getsize(ruta)
    if tamano > max_bytes:
        raise ErrorImagenVisual("Imagen excede max_bytes")

    formato, ancho, alto = inspeccionar_cabecera(ruta)
    if ancho > max_ancho or alto > max_alto:
        raise ErrorImagenVisual("Imagen excede dimensiones permitidas")
    if (ancho * alto) / 1000000.0 > max_megapixeles:
        raise ErrorImagenVisual("Imagen excede megapixeles permitidos")

    temp_path = None
    img = None
    try:
        from PIL import Image
        img = Image.open(ruta)
        img.load()
        img = img.convert("RGB")
        escala = min(1.0, max_lado_normalizado / float(max(ancho, alto)))
        nuevo_ancho = max(1, int(ancho * escala))
        nuevo_alto = max(1, int(alto * escala))
        if escala < 1.0:
            img = img.resize((nuevo_ancho, nuevo_alto))
        fd, temp_path = tempfile.mkstemp(
            prefix=".vision-", suffix=".jpg", dir=os.path.dirname(ruta)
        )
        os.close(fd)
        exif = getattr(img, "info", {})
        img.save(temp_path, format="JPEG", quality=88, exif=b"", optimize=True)
        huella = _huella(temp_path)
        return {
            "ruta_original": ruta,
            "ruta_normalizada": temp_path,
            "formato": formato,
            "ancho": nuevo_ancho,
            "alto": nuevo_alto,
            "ancho_original": ancho,
            "alto_original": alto,
            "tamano_original": tamano,
            "tamano_normalizado": os.path.getsize(temp_path),
            "huella": huella,
        }
    except ErrorImagenVisual:
        raise
    except Exception as exc:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        raise ErrorImagenVisual("No pudo normalizarse la imagen") from exc
    finally:
        if img is not None:
            try:
                img.close()
            except Exception:
                pass


def _huella(ruta: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def limpiar_normalizada(informacion: dict) -> None:
    ruta = informacion.get("ruta_normalizada")
    if ruta and os.path.exists(ruta):
        try:
            os.remove(ruta)
        except Exception:
            pass
