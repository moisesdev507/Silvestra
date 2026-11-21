"""Motor y procesador de comprension visual de interfaces."""
from __future__ import annotations

import collections
import threading
import time
from typing import Any, Optional

from percepcion_adaptadores import ProcesadorModalidad
from ui_visual_analizador import AnalizadorEstructuraUI
from ui_visual_comparador import ComparadorInterfazVisual
from ui_visual_modelo import MapaInterfazVisual, CambioInterfazVisual
import qt_estabilidad_ui


class MotorComprensionInterfaces:
    def __init__(self, analizador=None, comparador=None, max_entradas=16,
                 ttl_seg=60.0, app_cola=None, cerebro=None,
                 contexto_motor=None, orquestador=None,
                 motor_comprension_visual=None) -> None:
        self._bloqueo = threading.RLock()
        self.analizador = analizador or AnalizadorEstructuraUI()
        self.comparador = comparador or ComparadorInterfazVisual()
        self.max_entradas = max(1, int(max_entradas))
        self.ttl_seg = max(1.0, float(ttl_seg))
        self.app_cola = app_cola
        self.cerebro = cerebro
        self.contexto_motor = contexto_motor
        self.orquestador = orquestador
        self.motor_comprension_visual = motor_comprension_visual
        self._cache: collections.OrderedDict[str, MapaInterfazVisual] = (
            collections.OrderedDict()
        )
        self._cache_tiempos: dict[str, float] = {}

    def analizar_captura(self, ruta_imagen: str, hwnd=None,
                         metadatos=None, token_cancelacion=None
                         ) -> MapaInterfazVisual:
        anterior = self._ultimo_mapa()
        try:
            mapa = self.analizador.analizar(
                ruta_imagen, hwnd=hwnd, metadatos=metadatos,
                token_cancelacion=token_cancelacion,
            )
            mapa.ruta_captura = ""
            cambio = self.comparador.comparar(anterior, mapa)
            mapa.observaciones_verificables = list(
                mapa.observaciones_verificables
            )[:20]
            mapa.interpretaciones_inciertas = list(
                mapa.interpretaciones_inciertas
            )[:20]
            if cambio.pantalla_identica:
                mapa.observaciones_verificables.append(
                    "Captura identica a la anterior"
                )
            with self._bloqueo:
                self._cache[mapa.id_mapa] = mapa
                self._cache_tiempos[mapa.id_mapa] = time.time()
                self._cache.move_to_end(mapa.id_mapa)
                self._limpiar_vencidos()
                while len(self._cache) > self.max_entradas:
                    clave, _ = self._cache.popitem(last=False)
                    self._cache_tiempos.pop(clave, None)
            self._puente(mapa, cambio)
            return mapa
        finally:
            pass

    def _ultimo_mapa(self) -> Optional[MapaInterfazVisual]:
        with self._bloqueo:
            self._limpiar_vencidos()
            if not self._cache:
                return None
            clave, valor = next(reversed(self._cache.items()))
            if isinstance(valor, tuple):
                return valor[1]
            return valor

    def _limpiar_vencidos(self) -> None:
        ahora = time.time()
        vencidas = []
        for clave, mapa in self._cache.items():
            timestamp = self._cache_tiempos.get(clave)
            if timestamp is None:
                timestamp = getattr(mapa, "timestamp", ahora)
            if ahora - timestamp > self.ttl_seg:
                vencidas.append(clave)
        for clave in vencidas:
            self._cache.pop(clave, None)
            self._cache_tiempos.pop(clave, None)

    def obtener_mapa(self, id_mapa: str) -> Optional[MapaInterfazVisual]:
        with self._bloqueo:
            self._limpiar_vencidos()
            entrada = self._cache.get(id_mapa)
            if entrada is None:
                return None
            self._cache.move_to_end(id_mapa)
            return entrada[1] if isinstance(entrada, tuple) else entrada

    def responder_pregunta_interfaz(self, pregunta: str,
                                    id_mapa: str = "") -> str:
        pregunta_baja = str(pregunta or "").lower()
        mapa = self.obtener_mapa(id_mapa) if id_mapa else self._ultimo_mapa()
        if mapa is None:
            return "No hay capturas analizadas todavia."
        if mapa.protegida:
            return "La ventana o captura esta protegida y no puede analizarse."
        if any(p in pregunta_baja for p in ("aplicacion", "app", "programa")):
            return ("Aplicacion abierta: " +
                    (mapa.aplicacion or "no identificada") + ".")
        if any(p in pregunta_baja for p in ("ventana activa", "ventana",
                                            "titulo")):
            return ("Ventana activa: " +
                    (mapa.ventana_activa or "no identificada") + ".")
        if any(p in pregunta_baja for p in ("menu", "opciones")):
            menus = [e.nombre for e in mapa.elementos
                     if e.tipo.value in ("menu", "item_menu", "pestana")]
            return ("Opciones de menu: " + ", ".join(menus) + "."
                    if menus else "No aparece ninguna opcion de menu.")
        if any(p in pregunta_baja for p in ("boton", "ubicacion",
                                             "coordenada", "donde")):
            botones = [e for e in mapa.elementos if e.tipo.value == "boton"]
            if not botones:
                return "No aparece ningun boton."
            datos = []
            for boton in botones:
                if boton.region:
                    datos.append(
                        f"{boton.nombre or 'boton'} en ({boton.region.x}, "
                        f"{boton.region.y}), region normalizada "
                        f"{boton.region.x_normalizado:.2f},"
                        f"{boton.region.y_normalizado:.2f}"
                    )
            return "Ubicacion aproximada sin ejecutar acciones: " + "; ".join(datos) + "."
        if any(p in pregunta_baja for p in ("formulario", "campo", "contenido")):
            campos = []
            for formulario in mapa.formularios:
                for campo in formulario.campos:
                    campos.append(
                        (campo.nombre or "campo") + ": " + (campo.valor or "")
                    )
            return ("Formulario: " + "; ".join(campos) + "."
                    if campos else "No aparece ningun campo de formulario.")
        if any(p in pregunta_baja for p in ("error", "advertencia", "fallo")):
            if not mapa.alertas:
                return "No se observan errores ni advertencias visibles."
            return "Alertas visibles: " + "; ".join(
                f"{a.tipo}: {a.texto}" for a in mapa.alertas
            ) + "."
        if any(p in pregunta_baja for p in ("cambio", "diferencia", "anterior")):
            if len(self._cache) < 2:
                return "No hay una captura anterior para comparar."
            return "La interfaz presenta cambios respecto a la captura anterior."
        elementos = [e.nombre for e in mapa.elementos if e.nombre]
        return ("Interfaz detectada" +
                (": " + ", ".join(elementos[:8]) if elementos else "") + ".")

    def _puente(self, mapa: MapaInterfazVisual,
                cambio: CambioInterfazVisual) -> None:
        resumen = (
            f"{mapa.aplicacion or 'Aplicacion'} / "
            f"{mapa.ventana_activa or 'ventana'}: "
            f"{len(mapa.elementos)} componentes, {len(mapa.alertas)} alertas"
        )[:600]
        if self.app_cola is not None:
            try:
                payload = {"tipo": "ui_visual",
                           "mapa": mapa.a_dict(), "cambio": cambio.a_dict()}
                if hasattr(self.app_cola, "put_nowait"):
                    self.app_cola.put_nowait(("ui_visual_evento", payload))
                else:
                    self.app_cola.put(("ui_visual_evento", payload), block=False)
            except Exception:
                pass
        if self.cerebro is not None:
            try:
                self.cerebro.historial.append(
                    {"role": "system", "content": "[UI]" + resumen}
                )
            except Exception:
                pass
        if self.contexto_motor is not None:
            try:
                confirmar = getattr(self.contexto_motor,
                                    "confirmar_contexto", None)
                if callable(confirmar):
                    confirmar("percepcion_ui", mapa.a_dict(),
                              origen="ui_visual", ttl_seg=30)
            except Exception:
                pass
        if mapa.sugerencia_accion and self.orquestador is not None:
            try:
                recibir = getattr(self.orquestador, "recibir", None)
                if callable(recibir):
                    recibir(str(mapa.sugerencia_accion), origen="ui_visual",
                            requiere_ejecucion=False, modo="restringido")
            except Exception:
                pass


class ProcesadorInterfazVisual(ProcesadorModalidad):
    def __init__(self, motor: MotorComprensionInterfaces) -> None:
        self.motor = motor

    def procesar(self, evento, token_cancelacion=None) -> dict:
        ref = getattr(evento, "referencia_contenido", None)
        ruta = getattr(ref, "ruta", None) if ref is not None else None
        if not ruta:
            return {"error": "sin_ruta_visual"}
        mapa = self.motor.analizar_captura(
            ruta,
            metadatos=getattr(evento, "metadatos", {}),
            token_cancelacion=token_cancelacion,
        )
        return mapa.a_dict()
