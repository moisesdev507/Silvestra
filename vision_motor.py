"""Motor de comprension visual integrado con percepcion y Cerebro."""
from __future__ import annotations

import collections
import hashlib
import os
import threading
from typing import Any, Optional

from percepcion_adaptadores import ProcesadorModalidad
from vision_modelo import (
    SolicitudVisual,
    BloqueTextoOCR,
    ElementoVisual,
    ResultadoComprensionVisual,
)
from vision_imagen import (
    validar_y_normalizar,
    limpiar_normalizada,
)
from vision_ocr import MotorOCR, unir_texto
from vision_proveedores import AdaptadorProveedorVision


class MotorComprensionVisual:
    def __init__(
        self,
        proveedor: Optional[AdaptadorProveedorVision] = None,
        motor_ocr: Optional[MotorOCR] = None,
        sandbox=None,
        max_entradas: int = 16,
        app_cola=None,
        cerebro=None,
        contexto_motor=None,
        orquestador=None,
    ) -> None:
        self._bloqueo = threading.RLock()
        self.proveedor = proveedor
        self.motor_ocr = motor_ocr or MotorOCR()
        self.sandbox = sandbox
        self.max_entradas = max(1, int(max_entradas))
        self.app_cola = app_cola
        self.cerebro = cerebro
        self.contexto_motor = contexto_motor
        self.orquestador = orquestador
        self._cache: collections.OrderedDict[str, ResultadoComprensionVisual] = (
            collections.OrderedDict()
        )

    def procesar(
        self,
        solicitud: SolicitudVisual,
        token_cancelacion=None,
    ) -> ResultadoComprensionVisual:
        ref_original = solicitud.ruta_imagen
        normalizada = None
        try:
            normalizada = validar_y_normalizar(
                solicitud.ruta_imagen,
                sandbox=self.sandbox,
            )
            clave = solicitud.id_entrada + "|" + normalizada["huella"]
            with self._bloqueo:
                cached = self._cache.get(clave)
                if cached is not None:
                    self._cache.move_to_end(clave)
                    return cached

            if token_cancelacion and getattr(token_cancelacion, "is_set", lambda: False)():
                return ResultadoComprensionVisual(
                    solicitud.id_entrada,
                    os.path.basename(ref_original),
                    limitaciones=["Procesamiento cancelado"],
                    errores=["cancelado"],
                )

            bloques, limitaciones = self.motor_ocr.extraer(
                normalizada["ruta_normalizada"]
            )
            texto_extraido = unir_texto(bloques)
            observaciones = []
            interpretaciones = []
            descripcion = ""
            elementos = []
            confianza = None
            errores = []
            sugerencia = None

            if self.proveedor is not None:
                datos = self.proveedor.comprender(
                    pregunta=solicitud.pregunta,
                    ruta_imagen=normalizada["ruta_normalizada"],
                    contexto_breve=solicitud.contexto_breve,
                    autorizacion_externa=getattr(
                        solicitud, "autorizacion_externa", False
                    ),
                )
                if datos.get("error"):
                    errores.append(str(datos["error"])[:300])
                else:
                    descripcion = str(datos.get("descripcion", "")).strip()
                    if isinstance(datos.get("elementos"), list):
                        for item in datos["elementos"]:
                            if isinstance(item, dict):
                                elementos.append(ElementoVisual(
                                    nombre=str(item.get("nombre", "elemento")),
                                    categoria=str(item.get("categoria", "desconocido")),
                                    ubicacion_relativa=item.get("ubicacion"),
                                    verificable=bool(item.get("verificable", True)),
                                ))
                    if isinstance(datos.get("observaciones"), list):
                        observaciones = [
                            str(x) for x in datos["observaciones"][:20]
                        ]
                    if isinstance(datos.get("interpretaciones"), list):
                        interpretaciones = [
                            str(x) for x in datos["interpretaciones"][:20]
                        ]
                    valor_confianza = datos.get("confianza")
                    if isinstance(valor_confianza, (int, float)):
                        valor = float(valor_confianza)
                        confianza = valor if 0.0 <= valor <= 1.0 else None
                    if isinstance(datos.get("sugerencia_accion"), dict):
                        sugerencia = datos["sugerencia_accion"]

            if not descripcion:
                descripcion = "Analisis visual disponible"

            resultado = ResultadoComprensionVisual(
                id_entrada=solicitud.id_entrada,
                referencia_imagen=normalizada["huella"],
                descripcion=descripcion,
                elementos_identificados=elementos,
                texto_extraido=texto_extraido,
                bloques_ocr=bloques,
                observaciones_verificables=observaciones,
                interpretaciones_inciertas=interpretaciones,
                nivel_confianza=confianza,
                limitaciones=limitaciones,
                errores=errores,
                sugerencia_accion=sugerencia,
            )
            with self._bloqueo:
                self._cache[clave] = resultado
                self._cache.move_to_end(clave)
                while len(self._cache) > self.max_entradas:
                    self._cache.popitem(last=False)
            self._puente(resultado)
            return resultado
        except Exception as exc:
            return ResultadoComprensionVisual(
                id_entrada=solicitud.id_entrada,
                referencia_imagen=os.path.basename(ref_original),
                descripcion="",
                limitaciones=["No pudo procesarse la imagen"],
                errores=[str(exc)[:300]],
                nivel_confianza=None,
            )
        finally:
            if normalizada is not None:
                limpiar_normalizada(normalizada)

    def obtener_cached(
        self,
        id_entrada: str,
        huella_sha256: str,
    ) -> Optional[ResultadoComprensionVisual]:
        clave = id_entrada + "|" + huella_sha256
        with self._bloqueo:
            resultado = self._cache.get(clave)
            if resultado is not None:
                self._cache.move_to_end(clave)
            return resultado

    def _puente(self, resultado: ResultadoComprensionVisual) -> None:
        resumen = resultado.a_resumen_cerebro(600)
        if self.app_cola is not None:
            try:
                payload = {"tipo": "vision", "resultado": resultado.a_dict()}
                if hasattr(self.app_cola, "put_nowait"):
                    self.app_cola.put_nowait(("vision_evento", payload))
                else:
                    self.app_cola.put(("vision_evento", payload), block=False)
            except Exception:
                pass
        if self.cerebro is not None:
            try:
                self.cerebro.historial.append({
                    "role": "system",
                    "content": "[VISION] " + resumen,
                })
            except Exception:
                pass
        if self.contexto_motor is not None:
            try:
                confirmar = getattr(self.contexto_motor, "confirmar_contexto", None)
                if callable(confirmar):
                    confirmar(
                        "percepcion_visual",
                        resultado.a_dict(),
                        origen="vision",
                        ttl_seg=30.0,
                    )
            except Exception:
                pass
        if resultado.sugerencia_accion and self.orquestador is not None:
            try:
                recibir = getattr(self.orquestador, "recibir", None)
                if callable(recibir):
                    recibir(
                        str(resultado.sugerencia_accion),
                        origen="vision",
                        requiere_ejecucion=True,
                        modo="restringido",
                    )
            except Exception:
                pass


class ProcesadorComprensionVisual:
    def __init__(self, motor: MotorComprensionVisual) -> None:
        self.motor = motor

    def procesar(self, evento, token_cancelacion=None) -> dict:
        ruta = None
        ref = getattr(evento, "referencia_contenido", None)
        if ref is not None:
            ruta = getattr(ref, "ruta", None)
        if not ruta:
            return {"error": "sin_ruta_visual"}
        solicitud = SolicitudVisual(
            ruta_imagen=ruta,
            modalidad=(
                "captura_pantalla"
                if evento.modalidad == "captura_pantalla"
                else "imagen"
            ),
            pregunta=str(getattr(evento, "metadatos", {}).get("pregunta", "")),
            autorizacion_externa=bool(
                getattr(evento, "metadatos", {}).get(
                    "autorizacion_externa", False
                )
            ),
        )
        resultado = self.motor.procesar(solicitud, token_cancelacion)
        return resultado.a_dict()
