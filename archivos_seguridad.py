"""Sandbox y blindaje de rutas para operaciones controladas de archivos."""
from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Iterable, Optional


RESPALDOS_DIR = ".silvestra_respaldos"
UNIDADES_SIN_EXT = {".exe", ".bat", ".cmd", ".com", ".scr", ".ps1", ".vbs"}
EXTENSIONES_BLOQUEADAS = UNIDADES_SIN_EXT
NOMBRES_RESERVADOS = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class ErrorRutaArchivos(ValueError):
    pass


class ConfiguracionSandboxArchivos:
    def __init__(
        self,
        raices_permitidas: Optional[Iterable[str]] = None,
        extensiones_bloqueadas: Optional[Iterable[str]] = None,
        tamanio_maximo_lectura: int = 1024 * 1024,
    ) -> None:
        self.raices = tuple(
            os.path.abspath(os.path.realpath(str(r)))
            for r in (raices_permitidas or [])
            if str(r).strip()
        )
        self.extensiones_bloqueadas = {
            str(x).lower() if str(x).startswith(".") else "." + str(x).lower()
            for x in (extensiones_bloqueadas or EXTENSIONES_BLOQUEADAS)
        }
        self.tamanio_maximo_lectura = max(1, int(tamanio_maximo_lectura))

    def validar_nombre(self, nombre: str) -> str:
        texto = str(nombre or "").strip()
        if not texto or "\x00" in texto:
            raise ErrorRutaArchivos("Nombre vacio o contiene bytes nulos.")
        if texto in (".", ".."):
            raise ErrorRutaArchivos("Nombre reservado.")
        base = texto.split(".")[0].upper()
        if base in NOMBRES_RESERVADOS:
            raise ErrorRutaArchivos("Nombre reservado de Windows.")
        if any(c in texto for c in '<>"|?*'):
            raise ErrorRutaArchivos("Nombre contiene caracteres invalidos.")
        if texto.endswith((" ", ".")):
            raise ErrorRutaArchivos("Nombre termina con espacio o punto.")
        return texto

    def validar_ruta(self, ruta: str) -> str:
        if not isinstance(ruta, str) or not ruta.strip():
            raise ErrorRutaArchivos("Ruta vacia.")
        ruta = ruta.strip()
        if "\x00" in ruta:
            raise ErrorRutaArchivos("Ruta contiene bytes nulos.")
        if ruta.startswith(("\\\\", "//")):
            raise ErrorRutaArchivos("Rutas UNC no permitidas.")
        if ruta.lower().startswith("\\\\?\\") or ruta.lower().startswith("\\\\.\\"):
            raise ErrorRutaArchivos("Rutas de dispositivo no permitidas.")
        normal = ruta.replace("/", "\\")
        partes = re.split(r"[\\/]+", normal)
        if ".." in partes:
            raise ErrorRutaArchivos("Segmento '..' no permitido.")

        if re.search(r"^[A-Za-z]:[^\x00]*:", normal):
            raise ErrorRutaArchivos("Alternate Data Stream no permitido.")

        if not self.raices:
            raise ErrorRutaArchivos("Sandbox sin raices autorizadas.")

        candidato = os.path.abspath(os.path.realpath(ruta))
        contenido_raiz = None
        for raiz in self.raices:
            try:
                comun = os.path.commonpath((raiz, candidato))
            except (ValueError, OSError):
                continue
            if comun.lower() == raiz.lower():
                contenido_raiz = raiz
                break
        if contenido_raiz is None:
            raise ErrorRutaArchivos("Ruta fuera del sandbox autorizado.")

        raiz_abs = os.path.abspath(contenido_raiz)
        actual = raiz_abs
        relativo = os.path.relpath(candidato, raiz_abs)
        if relativo == ".":
            actual = raiz_abs
        else:
            for segmento in relativo.split(os.sep):
                if segmento in ("", "."):
                    continue
                actual = os.path.join(actual, segmento)
                self._bloquear_reparse(actual)

        nombre = os.path.basename(candidato)
        if nombre:
            self.validar_nombre(nombre)
        ext = os.path.splitext(nombre)[1].lower()
        if ext in self.extensiones_bloqueadas:
            raise ErrorRutaArchivos("Extension ejecutable o bloqueada.")
        if RESPALDOS_DIR in Path(candidato).parts:
            raise ErrorRutaArchivos("Directorio interno de respaldos no permitido.")
        return candidato

    def _bloquear_reparse(self, ruta: str) -> None:
        if not os.path.lexists(ruta):
            return
        if os.path.islink(ruta):
            raise ErrorRutaArchivos("Enlace simbolico no permitido.")
        if os.name == "nt":
            try:
                attrs = os.lstat(ruta).st_file_attributes
                if attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    raise ErrorRutaArchivos("Reparse point/junction no permitido.")
            except AttributeError:
                pass

    def validar_existente(self, ruta: str) -> str:
        valida = self.validar_ruta(ruta)
        if not os.path.lexists(valida):
            raise ErrorRutaArchivos("Ruta inexistente.")
        self._bloquear_reparse(valida)
        return valida

    def huella_estado(self, ruta: str) -> dict:
        valida = self.validar_existente(ruta)
        if not os.path.isfile(valida):
            raise ErrorRutaArchivos("Se esperaba un archivo.")
        st = os.stat(valida)
        h = hashlib.sha256()
        with open(valida, "rb") as f:
            for bloque in iter(lambda: f.read(65536), b""):
                h.update(bloque)
        return {"sha256": h.hexdigest(), "st_size": st.st_size,
                "st_mtime_ns": st.st_mtime_ns}

    def respaldos_dir(self, raiz_archivo: str) -> str:
        raiz = os.path.abspath(os.path.dirname(raiz_archivo))
        destino = os.path.join(raiz, RESPALDOS_DIR)
        os.makedirs(destino, exist_ok=True)
        return destino

    def escribir_atomico(self, ruta: str, datos: bytes) -> None:
        valida = self.validar_ruta(ruta)
        directorio = os.path.dirname(valida)
        fd, temporal = tempfile.mkstemp(prefix=".silvestra-", dir=directorio)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(datos)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporal, valida)
        except Exception:
            if os.path.exists(temporal):
                os.remove(temporal)
            raise
