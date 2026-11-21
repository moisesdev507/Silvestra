"""Modelos puros de comprension visual de interfaces."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TipoComponenteUI(str, Enum):
    VENTANA = "ventana"
    PANEL = "panel"
    PESTANA = "pestana"
    MENU = "menu"
    ITEM_MENU = "item_menu"
    BOTON = "boton"
    CAMPO_TEXTO = "campo_texto"
    TABLA = "tabla"
    CUADRO_DIALOGO = "cuadro_dialogo"
    NOTIFICACION = "notificacion"
    ICONO = "icono"
    ETIQUETA = "etiqueta"
    DESCONOCIDO = "desconocido"


@dataclass
class RegionVisualUI:
    x: int = 0
    y: int = 0
    ancho: int = 0
    alto: int = 0
    x_normalizado: float = 0.0
    y_normalizado: float = 0.0
    ancho_normalizado: float = 0.0
    alto_normalizado: float = 0.0
    centro: tuple[float, float] = field(default=(0.0, 0.0))

    def __post_init__(self) -> None:
        self.x, self.y = max(0, int(self.x)), max(0, int(self.y))
        self.ancho, self.alto = max(0, int(self.ancho)), max(0, int(self.alto))
        vals = (self.x_normalizado, self.y_normalizado,
                self.ancho_normalizado, self.alto_normalizado)
        vals = tuple(max(0.0, min(1.0, float(v))) for v in vals)
        self.x_normalizado, self.y_normalizado, self.ancho_normalizado, \
            self.alto_normalizado = vals
        if not self.centro or self.centro == (0.0, 0.0):
            self.centro = (
                float(self.x) + float(self.ancho) / 2.0,
                float(self.y) + float(self.alto) / 2.0,
            )

    def a_dict(self) -> dict:
        return {
            "x": self.x, "y": self.y, "ancho": self.ancho, "alto": self.alto,
            "x_normalizado": round(self.x_normalizado, 6),
            "y_normalizado": round(self.y_normalizado, 6),
            "ancho_normalizado": round(self.ancho_normalizado, 6),
            "alto_normalizado": round(self.alto_normalizado, 6),
            "centro": list(self.centro),
        }


@dataclass
class ElementoInterfazVisual:
    nombre: str = ""
    tipo: TipoComponenteUI = TipoComponenteUI.DESCONOCIDO
    valor: str = ""
    origen: str = "estructural_win32"
    region: Optional[RegionVisualUI] = None
    habilitado: bool = True
    padre: str = ""
    ruta_control: str = ""
    es_sensible: bool = False
    confianza: Optional[float] = None

    def __post_init__(self) -> None:
        if not isinstance(self.tipo, TipoComponenteUI):
            try:
                self.tipo = TipoComponenteUI(str(self.tipo).lower())
            except Exception:
                self.tipo = TipoComponenteUI.DESCONOCIDO
        if self.origen not in ("estructural_win32", "ocr", "vision_vlm"):
            self.origen = "ocr"
        if self.es_sensible:
            self.valor = "***" + str(len(str(self.valor or "")))

    def a_dict(self) -> dict:
        return {
            "nombre": str(self.nombre),
            "tipo": self.tipo.value,
            "valor": str(self.valor),
            "origen": self.origen,
            "region": self.region.a_dict() if self.region else None,
            "habilitado": bool(self.habilitado),
            "padre": str(self.padre),
            "ruta_control": str(self.ruta_control),
            "es_sensible": bool(self.es_sensible),
            "confianza": self.confianza,
        }


@dataclass
class FormularioVisualUI:
    nombre: str = ""
    campos: list[ElementoInterfazVisual] = field(default_factory=list)

    def a_dict(self) -> dict:
        return {"nombre": self.nombre, "campos": [c.a_dict() for c in self.campos]}


@dataclass
class AlertaInterfazUI:
    tipo: str = "notificacion"
    texto: str = ""
    region: Optional[RegionVisualUI] = None
    origen: str = "ocr"

    def __post_init__(self) -> None:
        if self.tipo not in ("error", "advertencia", "notificacion"):
            self.tipo = "notificacion"

    def a_dict(self) -> dict:
        return {"tipo": self.tipo, "texto": self.texto,
                "region": self.region.a_dict() if self.region else None,
                "origen": self.origen}


@dataclass
class MapaInterfazVisual:
    id_mapa: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    huella: str = ""
    hwnd: Optional[int] = None
    aplicacion: str = ""
    ventana_activa: str = ""
    ruta_captura: str = ""
    elementos: list[ElementoInterfazVisual] = field(default_factory=list)
    formularios: list[FormularioVisualUI] = field(default_factory=list)
    alertas: list[AlertaInterfazUI] = field(default_factory=list)
    observaciones_verificables: list[str] = field(default_factory=list)
    interpretaciones_inciertas: list[str] = field(default_factory=list)
    sugerencia_accion: Optional[dict] = None
    protegida: bool = False
    nivel_confianza: Optional[float] = None

    def a_dict(self) -> dict:
        return {
            "id_mapa": self.id_mapa, "timestamp": self.timestamp,
            "huella": self.huella, "hwnd": self.hwnd,
            "aplicacion": self.aplicacion, "ventana_activa": self.ventana_activa,
            "ruta_captura": "", "elementos": [e.a_dict() for e in self.elementos],
            "formularios": [f.a_dict() for f in self.formularios],
            "alertas": [a.a_dict() for a in self.alertas],
            "observaciones_verificables": list(self.observaciones_verificables),
            "interpretaciones_inciertas": list(self.interpretaciones_inciertas),
            "sugerencia_accion": self.sugerencia_accion,
            "protegida": bool(self.protegida),
            "nivel_confianza": self.nivel_confianza,
        }


@dataclass
class CambioInterfazVisual:
    timestamp: float = field(default_factory=time.time)
    ventana_cambio: bool = False
    alertas_nuevas: list[AlertaInterfazUI] = field(default_factory=list)
    componentes_anadidos: list[ElementoInterfazVisual] = field(default_factory=list)
    componentes_eliminados: list[ElementoInterfazVisual] = field(default_factory=list)
    cambios_campos: list[dict[str, Any]] = field(default_factory=list)
    huella_anterior: str = ""
    huella_nueva: str = ""
    puntuacion_cambio: float = 0.0
    pantalla_identica: bool = False

    def a_dict(self) -> dict:
        return {
            "timestamp": self.timestamp, "ventana_cambio": self.ventana_cambio,
            "alertas_nuevas": [a.a_dict() for a in self.alertas_nuevas],
            "componentes_anadidos": [e.a_dict() for e in self.componentes_anadidos],
            "componentes_eliminados": [e.a_dict() for e in self.componentes_eliminados],
            "cambios_campos": list(self.cambios_campos),
            "huella_anterior": self.huella_anterior,
            "huella_nueva": self.huella_nueva,
            "puntuacion_cambio": round(self.puntuacion_cambio, 4),
            "pantalla_identica": bool(self.pantalla_identica),
        }
