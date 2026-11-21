"""Comparacion semantica acotada de mapas y capturas visuales."""
from __future__ import annotations

import hashlib
import threading
from typing import Optional

from camara_comparador import ComparadorFotogramas
from ui_visual_modelo import (
    CambioInterfazVisual, MapaInterfazVisual, AlertaInterfazUI,
)


class ComparadorInterfazVisual:
    def __init__(self, comparador_frame=None) -> None:
        self._bloqueo = threading.RLock()
        self.comparador = comparador_frame or ComparadorFotogramas()
        self._anterior: Optional[MapaInterfazVisual] = None

    def huella_mapa(self, mapa: MapaInterfazVisual) -> str:
        canon = repr((
            mapa.aplicacion, mapa.ventana_activa,
            [(e.tipo.value, e.nombre, e.valor, e.region.a_dict()
              if e.region else None) for e in mapa.elementos],
            [a.a_dict() for a in mapa.alertas],
        ))
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()

    def comparar(self, anterior: Optional[MapaInterfazVisual],
                 nuevo: MapaInterfazVisual) -> CambioInterfazVisual:
        nuevo.huella = nuevo.huella or self.huella_mapa(nuevo)
        if anterior is None:
            anterior = self._anterior
        if anterior is None:
            cambio = CambioInterfazVisual(
                huella_nueva=nuevo.huella, puntuacion_cambio=1.0,
                componentes_anadidos=list(nuevo.elementos),
            )
            with self._bloqueo:
                self._anterior = nuevo
            return cambio
        anterior.huella = anterior.huella or self.huella_mapa(anterior)
        if anterior.huella == nuevo.huella:
            cambio = CambioInterfazVisual(
                huella_anterior=anterior.huella,
                huella_nueva=nuevo.huella,
                puntuacion_cambio=0.0,
                pantalla_identica=True,
            )
            with self._bloqueo:
                self._anterior = nuevo
            return cambio
        antiguos = {(e.tipo.value, e.nombre, e.valor): e for e in anterior.elementos}
        nuevos = {(e.tipo.value, e.nombre, e.valor): e for e in nuevo.elementos}
        anadidos = [n for clave, n in nuevos.items() if clave not in antiguos]
        eliminados = [a for clave, a in antiguos.items() if clave not in nuevos]
        claves_alertas = {(a.tipo, a.texto) for a in anterior.alertas}
        nuevas_alertas = [a for a in nuevo.alertas
                          if (a.tipo, a.texto) not in claves_alertas]
        campos_antes = {c.nombre: c.valor for c in anterior.elementos
                        if c.tipo.value == "campo_texto"}
        campos_despues = {c.nombre: c.valor for c in nuevo.elementos
                          if c.tipo.value == "campo_texto"}
        cambios_campos = [
            {"campo": nombre,
             "antes": campos_antes.get(nombre, ""),
             "despues": valor}
            for nombre, valor in campos_despues.items()
            if campos_antes.get(nombre, "") != valor
        ]
        cambio = CambioInterfazVisual(
            ventana_cambio=anterior.ventana_activa != nuevo.ventana_activa,
            alertas_nuevas=nuevas_alertas,
            componentes_anadidos=anadidos,
            componentes_eliminados=eliminados,
            cambios_campos=cambios_campos,
            huella_anterior=anterior.huella,
            huella_nueva=nuevo.huella,
            puntuacion_cambio=min(
                1.0, (len(anadidos) + len(eliminados) + len(nuevas_alertas)
                      + len(cambios_campos)) / 10.0,
            ),
        )
        with self._bloqueo:
            self._anterior = nuevo
        return cambio

    def comparar_capturas(self, ruta_anterior: str, ruta_nueva: str,
                          umbral: float = 0.12):
        from PIL import Image
        anteriores = nuevas = None
        try:
            anteriores = Image.open(ruta_anterior)
            nuevas = Image.open(ruta_nueva)
            self.comparador.reiniciar()
            primero = self.comparador.comparar(anteriores, umbral)
            segundo = self.comparador.comparar(nuevas, umbral)
            return segundo
        finally:
            for imagen in (anteriores, nuevas):
                if imagen is not None:
                    try:
                        imagen.close()
                    except Exception:
                        pass
