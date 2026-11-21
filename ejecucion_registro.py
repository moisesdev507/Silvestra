"""Registro, validacion y resolucion centralizada del nucleo de ejecucion."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Iterable, Optional

from ejecucion_modelo import (
    ESTADO_EN_EJECUCION,
    ESTADO_FALLIDA,
    ESTADO_COMPLETADA,
    ESTADO_RECHAZADA,
    ESTADO_VALIDADA,
    ESTADOS_SOLICITUD,
    ContratoHerramienta,
    ResultadoEjecucion,
    SolicitudEjecucion,
    resultado_error,
)
from ejecucion_esquemas import esquema_parametros, coincide_tipo


class RegistroHerramientas:
    """Registro central thread-safe de contratos uniformes."""

    def __init__(self) -> None:
        self._contratos: dict[str, ContratoHerramienta] = {}
        self._bloqueo = threading.RLock()

    def registrar(self, contrato: ContratoHerramienta, sobrescribir: bool = False) -> bool:
        if not isinstance(contrato, ContratoHerramienta):
            raise TypeError("contrato debe ser ContratoHerramienta")
        valido, motivo = contrato.valida_integridad()
        if not valido:
            raise ValueError(motivo)
        with self._bloqueo:
            if contrato.nombre in self._contratos and not sobrescribir:
                raise ValueError("Herramienta ya registrada: " + contrato.nombre)
            self._contratos[contrato.nombre] = contrato
            return True

    def obtener(self, nombre: str) -> Optional[ContratoHerramienta]:
        clave = str(nombre or "").strip().lower()
        with self._bloqueo:
            return self._contratos.get(clave)

    def listar(self, categoria: Optional[str] = None, solo_habilitadas: bool = True) -> list[ContratoHerramienta]:
        cat = str(categoria).strip().lower() if categoria is not None else None
        with self._bloqueo:
            contratos = list(self._contratos.values())
        if cat:
            contratos = [c for c in contratos if c.categoria == cat]
        if solo_habilitadas:
            contratos = [c for c in contratos if c.habilitada]
        return sorted(contratos, key=lambda c: c.nombre)

    def existe(self, nombre: str) -> bool:
        return self.obtener(nombre) is not None

    def inventariar_acciones(self, sobrescribir: bool = False) -> int:
        """Importa contratos aislados de acciones.py sin enlazar handlers reales."""
        from ejecucion_acciones import inventariar_acciones

        agregados = 0
        for contrato in inventariar_acciones():
            if not sobrescribir and self.existe(contrato.nombre):
                continue
            with self._bloqueo:
                self._contratos[contrato.nombre] = contrato
            agregados += 1
        return agregados

    def validar_solicitud(self, solicitud: SolicitudEjecucion) -> tuple[bool, str, Optional[ContratoHerramienta]]:
        if not isinstance(solicitud, SolicitudEjecucion):
            return False, "Solicitud no es SolicitudEjecucion.", None
        if solicitud.origen not in {"cerebro", "planificador", "usuario", "sistema"}:
            return False, "Origen de solicitud invalido.", None
        if solicitud.estado not in ESTADOS_SOLICITUD:
            return False, "Estado de solicitud invalido.", None
        if not solicitud.herramienta:
            return False, "Herramienta no especificada.", None

        contrato = self.obtener(solicitud.herramienta)
        if contrato is None:
            return False, "Herramienta inexistente.", None
        if not contrato.habilitada:
            return False, "Herramienta deshabilitada.", contrato

        requeridos, opcionales, tipos = esquema_parametros(contrato.parametros_esquema)
        permitidos = set(requeridos) | set(opcionales)
        for clave in solicitud.parametros:
            if clave not in permitidos:
                return False, f"Parametro inesperado: {clave}.", contrato
        for clave in requeridos:
            if clave not in solicitud.parametros:
                return False, f"Parametro obligatorio ausente: {clave}.", contrato

        for clave, valor in solicitud.parametros.items():
            especificacion = tipos.get(clave)
            if especificacion is None:
                continue
            if not coincide_tipo(valor, especificacion):
                return False, f"Tipo invalido para '{clave}'.", contrato
        return True, "", contrato


class ResolvedorEjecucion:
    """Resuelve solicitudes directas y derivadas de Tarea."""

    def __init__(self, registro: RegistroHerramientas) -> None:
        self.registro = registro

    def resolver_desde_tarea(self, tarea: Any, id_plan: Optional[str] = None) -> SolicitudEjecucion:
        datos = tarea.a_dict() if hasattr(tarea, "a_dict") else dict(tarea) if isinstance(tarea, dict) else {}
        herramienta = ""
        for clave in ("herramienta", "herramienta_ejecucion", "tool"):
            valor = getattr(tarea, clave, None)
            if valor:
                herramienta = str(valor).strip().lower()
                break
        for clave in ("herramienta", "herramienta_ejecucion", "tool"):
            valor = datos.get(clave)
            if valor:
                herramienta = str(valor).strip().lower()
                break

        if not herramienta:
            candidato = " ".join((
                str(datos.get("id_tarea", "")),
                str(datos.get("titulo", "")),
                str(datos.get("descripcion", "")),
            )).lower()
            coincidencias: list[tuple[int, str]] = []
            for contrato in self.registro.listar(solo_habilitadas=False):
                nombre = contrato.nombre
                if nombre in candidato:
                    coincidencias.append((len(nombre), nombre))
                elif nombre.replace("_", " ") in candidato:
                    coincidencias.append((len(nombre), nombre))
            if coincidencias:
                herramienta = max(coincidencias)[1]

        parametros = datos.get("parametros", {})
        if not isinstance(parametros, dict):
            parametros = {}
        return SolicitudEjecucion(
            origen="planificador",
            herramienta=herramienta,
            parametros=parametros,
            id_plan=str(id_plan) if id_plan else None,
            id_tarea=str(datos.get("id_tarea", "")) or None,
        )


class SistemaEjecucion:
    """Valida y ejecuta solo handlers registrados y seguros/dry-run por contrato."""

    def __init__(
        self,
        registro: Optional[RegistroHerramientas] = None,
        pre_validacion: Optional[Callable[..., Any]] = None,
        post_ejecucion: Optional[Callable[..., Any]] = None,
        motor_permisos: Optional[Any] = None,
    ) -> None:
        self.registro = registro or RegistroHerramientas()
        self.resolvedor = ResolvedorEjecucion(self.registro)
        self.pre_validacion = pre_validacion
        self.post_ejecucion = post_ejecucion
        self.motor_permisos = motor_permisos

    def resolver_desde_tarea(self, tarea: Any, id_plan: Optional[str] = None) -> SolicitudEjecucion:
        return self.resolvedor.resolver_desde_tarea(tarea, id_plan)

    def _validar_motor_fallback(
        self, solicitud: SolicitudEjecucion, contrato: ContratoHerramienta
    ) -> dict[str, Any]:
        d = self.motor_permisos.evaluar_solicitud(solicitud, contrato)
        if d.get("decision") == "pendiente_autorizacion":
            return {"estado": "pendiente", **d}
        if d.get("decision") != "permitida":
            return {"estado": "rechazada", **d}
        v = self.motor_permisos.validar_antes_de_ejecutar(solicitud, contrato)
        return {"estado": "permitida" if v.get("permitida") else "rechazada", **v}

    def procesar(self, solicitud: SolicitudEjecucion) -> ResultadoEjecucion:
        inicio = time.perf_counter()
        metadatos: dict[str, Any] = {}
        try:
            if isinstance(solicitud, dict):
                solicitud = SolicitudEjecucion.de_dict(solicitud)
            valido, motivo, contrato = self.registro.validar_solicitud(solicitud)
            if contrato is not None:
                metadatos = contrato.metadatos()
            if not valido:
                codigo = (
                    "HERRAMIENTA_INEXISTENTE" if motivo == "Herramienta inexistente." else
                    "HERRAMIENTA_DESHABILITADA" if motivo == "Herramienta deshabilitada." else
                    "PARAMETROS_INVALIDOS" if "Parametro" in motivo or "Tipo" in motivo else
                    "SOLICITUD_MALFORMADA"
                )
                duracion = (time.perf_counter() - inicio) * 1000.0
                return resultado_error(solicitud, codigo, motivo, True, duracion, metadatos)

            solicitud.estado = ESTADO_VALIDADA
            if self.motor_permisos is not None:
                try:
                    metodo_integracion = getattr(
                        self.motor_permisos, "validar_para_ejecucion", None
                    )
                    permiso = (
                        metodo_integracion(solicitud, contrato)
                        if callable(metodo_integracion)
                        else self._validar_motor_fallback(solicitud, contrato)
                    )
                    estado_permiso = permiso.get("estado")
                    if estado_permiso == "pendiente":
                        solicitud.estado = "pendiente_autorizacion"
                        duracion = (time.perf_counter() - inicio) * 1000.0
                        return ResultadoEjecucion(
                            solicitud.id_solicitud, solicitud.herramienta,
                            "pendiente_autorizacion", False, None,
                            {"codigo": "PENDIENTE_AUTORIZACION",
                             "mensaje": "Requiere confirmacion explicita del usuario.",
                             "recuperable": True},
                            duracion, {**metadatos, **permiso},
                        )
                    if estado_permiso == "rechazada":
                        solicitud.estado = ESTADO_RECHAZADA
                        duracion = (time.perf_counter() - inicio) * 1000.0
                        return resultado_error(
                            solicitud,
                            permiso.get("motivo", permiso.get("codigo", "DENEGADA")),
                            "Solicitud denegada por politica de seguridad.",
                            True, duracion, {**metadatos, **permiso},
                        )
                except Exception:
                    solicitud.estado = ESTADO_RECHAZADA
                    duracion = (time.perf_counter() - inicio) * 1000.0
                    return resultado_error(
                        solicitud, "ERROR_INTERNO_PERMISOS",
                        "Motor de permisos fallido en modo fail-closed.",
                        True, duracion, metadatos,
                    )
            if callable(self.pre_validacion):
                pre = self.pre_validacion(solicitud, contrato)
                if isinstance(pre, tuple) and len(pre) == 2 and pre[0] is False:
                    duracion = (time.perf_counter() - inicio) * 1000.0
                    solicitud.estado = ESTADO_RECHAZADA
                    return resultado_error(
                        solicitud, "RECHAZADO_PRE_VALIDACION", str(pre[1]), True, duracion, metadatos
                    )

            solicitud.estado = ESTADO_EN_EJECUCION
            if contrato.handler is None:
                datos = {
                    "modo": "informativo",
                    "descripcion": contrato.descripcion,
                    "simulado": True,
                }
            else:
                datos = contrato.handler(dict(solicitud.parametros))

            solicitud.estado = ESTADO_COMPLETADA
            duracion = (time.perf_counter() - inicio) * 1000.0
            resultado = ResultadoEjecucion(
                id_solicitud=solicitud.id_solicitud,
                herramienta=solicitud.herramienta,
                estado=ESTADO_COMPLETADA,
                exito=True,
                datos=datos,
                error=None,
                duracion_ms=duracion,
                metadatos=metadatos,
            )
            if callable(self.post_ejecucion):
                try:
                    self.post_ejecucion(solicitud, contrato, resultado)
                except Exception:
                    pass
            return resultado
        except Exception as exc:
            duracion = (time.perf_counter() - inicio) * 1000.0
            solicitud.estado = ESTADO_FALLIDA
            resultado = ResultadoEjecucion(
                id_solicitud=solicitud.id_solicitud,
                herramienta=solicitud.herramienta,
                estado=ESTADO_FALLIDA,
                exito=False,
                datos=None,
                error={
                    "codigo": "ERROR_INTERNO_HANDLER",
                    "mensaje": "El handler seguro lanzo una excepcion controlada.",
                    "recuperable": True,
                },
                duracion_ms=duracion,
                metadatos=metadatos,
            )
            return resultado
