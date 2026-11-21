"""Adaptadores extensibles y validacion de entradas perceptivas."""
from __future__ import annotations

import os
import threading
from typing import Any, Callable, Optional

from percepcion_modelo import (
    DESCARTADO,
    EventoPerceptivo,
    PoliticaRecursosModalidad,
    ReferenciaContenido,
)


class ErrorEntradaPerceptiva(ValueError):
    pass


class ProcesadorModalidad:
    def procesar(self, evento: EventoPerceptivo,
                 token_cancelacion=None) -> dict[str, Any]:
        raise NotImplementedError


class RegistroAdaptadoresPercepcion:
    def __init__(self) -> None:
        self._bloqueo = threading.RLock()
        self._procesadores: dict[str, ProcesadorModalidad] = {}
        self._fuentes: dict[str, bool] = {}
        self._modalidades: dict[str, bool] = {}
        self._politicas: dict[str, PoliticaRecursosModalidad] = {}

    def registrar(self, modalidad: str, procesador: ProcesadorModalidad,
                  politica: Optional[PoliticaRecursosModalidad] = None,
                  sobrescribir: bool = False) -> bool:
        modalidad = str(modalidad).strip().lower()
        if not callable(getattr(procesador, "procesar", None)):
            raise TypeError("ProcesadorModalidad invalido")
        with self._bloqueo:
            if modalidad in self._procesadores and not sobrescribir:
                raise ValueError("Adaptador ya registrado: " + modalidad)
            self._procesadores[modalidad] = procesador
            self._modalidades[modalidad] = True
            self._politicas[modalidad] = politica or PoliticaRecursosModalidad()
        return True

    def habilitar_fuente(self, fuente: str) -> None:
        with self._bloqueo:
            self._fuentes[str(fuente)] = True

    def deshabilitar_fuente(self, fuente: str) -> None:
        with self._bloqueo:
            self._fuentes[str(fuente)] = True
            self._fuentes[str(fuente)] = False

    def habilitar_modalidad(self, modalidad: str) -> None:
        with self._bloqueo:
            self._modalidades[str(modalidad).lower()] = True

    def deshabilitar_modalidad(self, modalidad: str) -> None:
        with self._bloqueo:
            self._modalidades[str(modalidad).lower()] = False

    def esta_habilitada(self, fuente: str = "", modalidad: str = "") -> bool:
        with self._bloqueo:
            if modalidad and not self._modalidades.get(modalidad.lower(), True):
                return False
            if fuente and not self._fuentes.get(fuente, True):
                return False
        return True

    def obtener(self, modalidad: str) -> Optional[ProcesadorModalidad]:
        with self._bloqueo:
            return self._procesadores.get(modalidad.lower())

    def obtener_politica(self, modalidad: str) -> PoliticaRecursosModalidad:
        with self._bloqueo:
            return self._politicas.get(modalidad.lower(),
                                      PoliticaRecursosModalidad())


def _validar_archivo(ruta: str, max_bytes: int, sandbox=None) -> tuple[str, int]:
    if not isinstance(ruta, str) or not ruta.strip():
        raise ErrorEntradaPerceptiva("Ruta inexistente")
    if "\x00" in ruta:
        raise ErrorEntradaPerceptiva("Ruta contiene bytes nulos")
    normal = ruta.replace("/", "\\")
    if ".." in normal.replace("\\", "/").split("/"):
        raise ErrorEntradaPerceptiva("Traversal no permitido")
    if ruta.startswith(("\\\\", "//")):
        raise ErrorEntradaPerceptiva("Ruta UNC no permitida")
    if sandbox is not None:
        try:
            ruta = sandbox.validar_existente(ruta)
        except Exception as exc:
            raise ErrorEntradaPerceptiva(str(exc))
    else:
        ruta = os.path.abspath(os.path.realpath(ruta))
    if not os.path.isfile(ruta):
        raise ErrorEntradaPerceptiva("Archivo inexistente")
    tamano = os.path.getsize(ruta)
    if tamano > max_bytes:
        raise ErrorEntradaPerceptiva("Entrada excede max_bytes")
    return ruta, tamano


class AdaptadorArchivoBase:
    def __init__(self, modalidad: str, sandbox=None) -> None:
        self.modalidad = modalidad
        self.sandbox = sandbox

    def crear_evento(
        self,
        fuente: str,
        ruta: Optional[str] = None,
        prioridad: int = 0,
        duracion_seg: float = 0.0,
        metadatos: Optional[dict] = None,
        max_bytes: int = 5 * 1024 * 1024,
    ) -> EventoPerceptivo:
        referencia = None
        if ruta:
            ruta, tamano = _validar_archivo(ruta, max_bytes, self.sandbox)
            referencia = ReferenciaContenido(
                ruta=ruta,
                tipo=self.modalidad,
                tamano=tamano,
                duracion_seg=float(duracion_seg),
            )
        evento = EventoPerceptivo(
            modalidad=self.modalidad,
            fuente=fuente,
            prioridad=prioridad,
            metadatos=metadatos or {},
            referencia_contenido=referencia,
        )
        if referencia:
            import hashlib
            h = hashlib.sha256()
            if os.path.isfile(referencia.ruta):
                with open(referencia.ruta, "rb") as f:
                    for bloque in iter(lambda: f.read(65536), b""):
                        h.update(bloque)
            referencia.huella = h.hexdigest()
            evento.huella_sha256 = referencia.huella
        return evento


class AdaptadorImagen(AdaptadorArchivoBase):
    def __init__(self, sandbox=None):
        super().__init__("imagen", sandbox)


class AdaptadorCamara(AdaptadorArchivoBase):
    def __init__(self, sandbox=None):
        super().__init__("camara", sandbox)


class AdaptadorCapturaPantalla(AdaptadorArchivoBase):
    def __init__(self, sandbox=None):
        super().__init__("captura_pantalla", sandbox)


class AdaptadorAudio(AdaptadorArchivoBase):
    def __init__(self, sandbox=None):
        super().__init__("audio", sandbox)


class AdaptadorContextoSistema:
    def crear_evento(self, fuente: str, metadatos: dict,
                     prioridad: int = 0) -> EventoPerceptivo:
        return EventoPerceptivo(
            modalidad="contexto_sistema",
            fuente=fuente,
            prioridad=prioridad,
            metadatos=metadatos,
        )


class AdaptadorEventoComponente:
    def crear_evento(self, fuente: str, metadatos: dict,
                     prioridad: int = 0) -> EventoPerceptivo:
        return EventoPerceptivo(
            modalidad="evento_interno",
            fuente=fuente,
            prioridad=prioridad,
            metadatos=metadatos,
        )
