"""Registro y verificadores independientes de evidencia real."""
from __future__ import annotations

import os
import threading
from typing import Any, Callable, Optional

from verificacion_modelo import EvidenciaVerificacion


class RegistroEstrategiasVerificacion:
    def __init__(self) -> None:
        self._bloqueo = threading.RLock()
        self._criterios: dict[str, Any] = {}
        self._verificadores: dict[str, Callable[..., EvidenciaVerificacion]] = {}

    def registrar(
        self,
        criterio: Any,
        verificador: Callable[..., EvidenciaVerificacion],
        sobrescribir: bool = False,
    ) -> bool:
        if not callable(verificador):
            raise TypeError("verificador debe ser callable")
        nombre = getattr(criterio, "herramienta", "")
        if not nombre:
            raise ValueError("criterio sin herramienta")
        with self._bloqueo:
            if nombre in self._verificadores and not sobrescribir:
                raise ValueError("Estrategia ya registrada: " + nombre)
            self._criterios[nombre] = criterio
            self._verificadores[nombre] = verificador
        return True

    def obtener_criterio(self, herramienta: str) -> Optional[Any]:
        with self._bloqueo:
            return self._criterios.get(str(herramienta).strip().lower())

    def verificar(
        self,
        herramienta: str,
        solicitud: Any,
        resultado: Any,
        esperado: Any = None,
    ) -> EvidenciaVerificacion:
        clave = str(herramienta).strip().lower()
        with self._bloqueo:
            verificador = self._verificadores.get(clave)
        if verificador is None:
            return EvidenciaVerificacion(
                fuente="sin_verificador",
                verificada=False,
                coincide_esperado=False,
                insuficiente=True,
                datos={"motivo": "verificador ausente"},
            )
        try:
            evidencia = verificador(solicitud, resultado, esperado)
            if not isinstance(evidencia, EvidenciaVerificacion):
                raise TypeError("verificador devolvio tipo invalido")
            return evidencia
        except Exception as exc:
            return EvidenciaVerificacion(
                fuente=clave,
                verificada=False,
                coincide_esperado=False,
                insuficiente=True,
                datos={"motivo": "error en verificador"},
            )


def verificar_archivo(
    ruta: str,
    existe: bool = True,
    sha256_esperado: Optional[str] = None,
    tamano_esperado: Optional[int] = None,
) -> EvidenciaVerificacion:
    try:
        from archivos_seguridad import ConfiguracionSandboxArchivos
        if not ruta or not os.path.exists(ruta):
            return EvidenciaVerificacion(
                "archivo", existe is False, existe is False,
                datos={"ruta": os.path.basename(ruta)},
            )
        if not os.path.isfile(ruta):
            return EvidenciaVerificacion(
                "archivo", False, False, insuficiente=True,
                datos={"ruta": os.path.basename(ruta)},
            )
        st = os.stat(ruta)
        coincide = True
        if tamano_esperado is not None:
            coincide = coincide and st.st_size == int(tamano_esperado)
        if sha256_esperado:
            import hashlib
            h = hashlib.sha256()
            with open(ruta, "rb") as f:
                for bloque in iter(lambda: f.read(65536), b""):
                    h.update(bloque)
            coincide = coincide and h.hexdigest() == sha256_esperado
        return EvidenciaVerificacion(
            "archivo", True, coincide,
            datos={"tamano": st.st_size, "nombre": os.path.basename(ruta)},
        )
    except Exception:
        return EvidenciaVerificacion(
            "archivo", False, False, insuficiente=True,
            datos={"motivo": "insuficiente"},
        )


def verificar_proceso(
    identidad: Any,
    supervisor: Any,
) -> EvidenciaVerificacion:
    try:
        registro = supervisor.obtener(getattr(identidad, "pid", 0))
        if registro is None:
            return EvidenciaVerificacion(
                "proceso", False, False, insuficiente=True,
                datos={"motivo": "proceso no registrado"},
            )
        actual = getattr(registro, "identidad", None)
        coincide = (
            actual is not None
            and actual.pid == identidad.pid
            and actual.creado_en_ns == identidad.creado_en_ns
            and os.path.realpath(actual.ruta_ejecutable).lower()
            == os.path.realpath(identidad.ruta_ejecutable).lower()
            and getattr(registro, "estado", "") in ("ejecutando", "finalizado")
        )
        return EvidenciaVerificacion(
            "proceso", True, coincide,
            es_parcial=getattr(registro, "estado", "") == "finalizado",
            datos={"pid": identidad.pid, "estado": getattr(registro, "estado", "")},
        )
    except Exception:
        return EvidenciaVerificacion(
            "proceso", False, False, insuficiente=True,
            datos={"motivo": "insuficiente"},
        )
