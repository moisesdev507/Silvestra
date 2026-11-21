"""Analizador estructural y OCR de interfaces Windows sin acciones."""
from __future__ import annotations

import os
import re
from typing import Any, Optional

from gui_seguridad import (
    CLASES_PROHIBIDAS, ValidadorGui, titulo_es_sensible,
)
from gui_ventanas import ventana_activa
from gui_inspeccion import inspeccionar_interfaz
from contexto_windows import obtener_contexto_windows
from vision_ocr import MotorOCR
from ui_visual_modelo import (
    TipoComponenteUI, RegionVisualUI, ElementoInterfazVisual,
    FormularioVisualUI, AlertaInterfazUI, MapaInterfazVisual,
)

CLAVES_SENSIBLES = ("password", "contrasena", "contraseña", "token",
                    "clave", "pin", "secret", "api_key")


def sanitizar_nombre_valor(nombre: str, valor: str = "") -> tuple[str, bool]:
    nombre_limpio = str(nombre or "").strip()
    bajo = nombre_limpio.lower()
    sensible = any(clave in bajo for clave in CLAVES_SENSIBLES)
    limpio = "***" + str(len(str(valor or ""))) if sensible else str(valor or "")
    return limpio, sensible


class AnalizadorEstructuraUI:
    def __init__(self, motor_ocr=None, proveedor=None, catalogo=None,
                 supervisor=None, autorizacion_externa=False,
                 validador=None) -> None:
        self.motor_ocr = motor_ocr or MotorOCR()
        self.proveedor = proveedor
        self.catalogo = catalogo
        self.supervisor = supervisor
        self.autorizacion_externa = bool(autorizacion_externa)
        self.validador = validador

    def _ventana(self, hwnd=None) -> dict:
        if hwnd is not None:
            parametros = {"hwnd": int(hwnd), "_catalogo": self.catalogo,
                          "_supervisor": self.supervisor}
            try:
                if self.catalogo is not None or self.supervisor is not None:
                    inspeccion = inspeccionar_interfaz(parametros)
                else:
                    inspeccion = {"elementos": []}
            except Exception:
                inspeccion = {"elementos": []}
            datos = obtener_contexto_windows()
            return {"hwnd": int(hwnd), "titulo": datos.get("titulo", ""),
                    "ejecutable": datos.get("ejecutable", ""),
                    "clase": "", "inspeccion": inspeccion}
        if self.catalogo is not None or self.supervisor is not None:
            datos = ventana_activa({
                "_catalogo": self.catalogo, "_supervisor": self.supervisor,
            })
        else:
            datos = obtener_contexto_windows()
            datos = {"hwnd": datos.get("hwnd"),
                     "titulo": datos.get("titulo", ""),
                     "identidad": {"ruta_ejecutable": datos.get("ejecutable", "")},
                     "clase": "", "protegida": False}
        inspeccion = {"elementos": []}
        hwnd = datos.get("hwnd")
        if hwnd and not datos.get("protegida"):
            try:
                inspeccion = inspeccionar_interfaz({
                    "hwnd": hwnd, "_catalogo": self.catalogo,
                    "_supervisor": self.supervisor,
                })
            except Exception:
                pass
        return {**datos, "inspeccion": inspeccion}

    def validar_ventana(self, datos: dict) -> tuple[bool, str]:
        hwnd = int(datos.get("hwnd") or 0)
        if hwnd <= 0:
            return False, "VENTANA_NO_VISIBLE"
        clase = str(datos.get("clase", "") or "")
        if clase in CLASES_PROHIBIDAS:
            return False, "ESCRITORIO_PROTEGIDO"
        titulo = str(datos.get("titulo", "") or "")
        if titulo_es_sensible(titulo):
            return False, "VENTANA_PROTEGIDA"
        if datos.get("protegida"):
            return False, "VENTANA_PROTEGIDA"
        if self.catalogo is not None or self.supervisor is not None:
            try:
                ValidadorGui(self.catalogo, self.supervisor).validar_hwnd(hwnd)
            except Exception as exc:
                return False, str(exc)
        return True, ""

    def analizar(self, ruta_imagen: str, hwnd=None,
                 metadatos: Optional[dict] = None,
                 token_cancelacion=None) -> MapaInterfazVisual:
        datos = self._ventana(hwnd)
        metadatos = metadatos or {}
        if metadatos.get("hwnd") is not None:
            datos["hwnd"] = int(metadatos["hwnd"] or datos.get("hwnd") or 0)
        for clave_dato, clave_meta in (
            ("titulo", "ventana_activa"), ("titulo", "titulo"),
            ("ejecutable", "aplicacion"),
        ):
            if metadatos.get(clave_meta):
                datos[clave_dato] = str(metadatos[clave_meta])
        if metadatos.get("clase"):
            datos["clase"] = str(metadatos["clase"])
        if metadatos.get("protegida") is not None:
            datos["protegida"] = bool(metadatos["protegida"])
        valida, motivo = self.validar_ventana(datos)
        if not valida:
            return MapaInterfazVisual(
                hwnd=int(datos.get("hwnd") or 0),
                aplicacion=str(datos.get("ejecutable", "") or ""),
                ventana_activa=str(datos.get("titulo", "") or ""),
                protegida=True,
                observaciones_verificables=[],
                interpretaciones_inciertas=[],
            )
        elementos = self._estructurales(datos)
        bloques = []
        limitaciones = []
        if token_cancelacion and getattr(token_cancelacion, "is_set",
                                         lambda: False)():
            return MapaInterfazVisual(protegida=True,
                                      interpretaciones_inciertas=["cancelado"])
        bloques, limitaciones = self.motor_ocr.extraer(ruta_imagen)
        elementos.extend(self._ocr(bloques))
        descripcion = ""
        observaciones = []
        interpretaciones = []
        confianza = None
        if self.proveedor is not None:
            try:
                respuesta = self.proveedor.comprender(
                    pregunta="Describe componentes, formulario y alertas",
                    ruta_imagen=ruta_imagen,
                    contexto_breve="Interfaz grafica Windows",
                    autorizacion_externa=self.autorizacion_externa,
                )
            except TypeError:
                respuesta = self.proveedor.comprender(
                    pregunta="Describe componentes, formulario y alertas",
                    ruta_imagen=ruta_imagen,
                    contexto_breve="Interfaz grafica Windows",
                )
            if respuesta.get("error"):
                limitaciones.append(str(respuesta["error"])[:300])
            else:
                descripcion = str(respuesta.get("descripcion", "")).strip()
                observaciones = [str(x) for x in respuesta.get(
                    "observaciones", [])[:20]]
                interpretaciones = [str(x) for x in respuesta.get(
                    "interpretaciones", [])[:20]]
                valor = respuesta.get("confianza")
                if isinstance(valor, (int, float)):
                    valor = float(valor)
                    confianza = valor if 0 <= valor <= 1 else None
        formularios, alertas = self._agrupar(elementos, observaciones,
                                               descripcion)
        app = str(datos.get("ejecutable", "") or "")
        ventana = str(datos.get("titulo", "") or "")
        return MapaInterfazVisual(
            hwnd=int(datos.get("hwnd") or 0),
            aplicacion=os.path.basename(app) if app else "",
            ventana_activa=ventana,
            elementos=elementos,
            formularios=formularios,
            alertas=alertas,
            observaciones_verificables=observaciones,
            interpretaciones_inciertas=interpretaciones,
            nivel_confianza=confianza,
        )

    def _estructurales(self, datos: dict) -> list[ElementoInterfazVisual]:
        elementos = []
        rect_window = datos.get("rect") or (0, 0, 0, 0)
        ancho = max(1, int(rect_window[2] - rect_window[0])) if rect_window else 1
        alto = max(1, int(rect_window[3] - rect_window[1])) if rect_window else 1
        for item in datos.get("inspeccion", {}).get("elementos", []):
            tipo_txt = str(item.get("tipo", "desconocido")).lower()
            mapa_tipo = {
                "button": "boton", "boton": "boton", "edit": "campo_texto",
                "campo_texto": "campo_texto", "static": "etiqueta",
                "etiqueta": "etiqueta", "list": "tabla",
                "lista": "tabla", "combobox": "pestana",
            }
            tipo = mapa_tipo.get(tipo_txt, "desconocido")
            nombre = str(item.get("nombre", "") or "")
            valor, sensible = sanitizar_nombre_valor(
                nombre, item.get("valor", nombre)
            )
            rr = item.get("rect_relativo") or {}
            x, y = int(rr.get("x", 0)), int(rr.get("y", 0))
            w, h = int(rr.get("ancho", 0)), int(rr.get("alto", 0))
            region = RegionVisualUI(
                x=x, y=y, ancho=w, alto=h,
                x_normalizado=x / ancho, y_normalizado=y / alto,
                ancho_normalizado=w / ancho, alto_normalizado=h / alto,
            )
            elementos.append(ElementoInterfazVisual(
                nombre=nombre if not sensible else "***",
                tipo=tipo, valor=valor, origen="estructural_win32",
                region=region, habilitado=bool(item.get("habilitado", True)),
                padre=str(item.get("ruta_control", "")).rsplit("/", 1)[0],
                ruta_control=str(item.get("ruta_control", "")),
                es_sensible=sensible,
            ))
        return elementos

    def _ocr(self, bloques) -> list[ElementoInterfazVisual]:
        elementos = []
        for bloque in bloques:
            texto = str(getattr(bloque, "texto", "") or "").strip()
            if not texto:
                continue
            regiones = getattr(bloque, "region", None)
            region = None
            if isinstance(regiones, dict):
                region = RegionVisualUI(
                    x=int(regiones.get("x", 0)), y=int(regiones.get("y", 0)),
                    ancho=int(regiones.get("ancho", 0)),
                    alto=int(regiones.get("alto", 0)),
                )
            limpio, sensible = sanitizar_nombre_valor(texto, texto)
            elementos.append(ElementoInterfazVisual(
                nombre="***" if sensible else texto,
                tipo=TipoComponenteUI.ETIQUETA,
                valor=limpio, origen="ocr", region=region,
                es_sensible=sensible,
            ))
        return elementos

    def _agrupar(self, elementos, observaciones, descripcion):
        campos = [e for e in elementos
                  if e.tipo == TipoComponenteUI.CAMPO_TEXTO]
        formularios = [FormularioVisualUI("Formulario", campos)] if campos else []
        alertas = []
        patron = re.compile(r"(?i)\b(error|advertencia|aviso|fallo)\b")
        textos = [e.nombre for e in elementos if e.nombre]
        textos.extend(str(x) for x in observaciones)
        if descripcion:
            textos.append(descripcion)
        for texto in textos:
            coincidencia = patron.search(texto)
            if coincidencia:
                tipo = "error" if coincidencia.group(1).lower() in (
                    "error", "fallo") else "advertencia"
                alertas.append(AlertaInterfazUI(tipo=tipo, texto=texto))
        return formularios, alertas
