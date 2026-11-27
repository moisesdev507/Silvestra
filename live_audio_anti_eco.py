"""Compuerta anti-eco half-duplex extraída de live_audio sin cambiar lógica."""
import os
import time
from typing import Optional


class CompuertaAntiEco:
    """Compuerta half-duplex para evitar autocorte por eco con parlantes."""

    def __init__(
        self,
        modo_audifonos: Optional[bool] = None,
        eco_cola_ms: Optional[float] = None,
        cola_salida=None,
    ):
        if modo_audifonos is None:
            self.modo_audifonos = os.environ.get("KAYA_MODO_AUDIFONOS", "0").strip() == "1"
        else:
            self.modo_audifonos = bool(modo_audifonos)

        if eco_cola_ms is None:
            try:
                self.eco_cola_ms = float(os.environ.get("KAYA_ECO_COLA_MS", "150"))
            except Exception:
                self.eco_cola_ms = 150.0
        else:
            self.eco_cola_ms = float(eco_cola_ms)

        self.cola_salida = cola_salida
        self._reproduciendo_salida = False
        self._ultimo_fin_salida = 0.0
        self._abierta = False

    def marcar_inicio_escritura(self):
        """Marca inicio de reproducción al parlante."""
        self._reproduciendo_salida = True
        self._ultimo_fin_salida = time.monotonic()
        self._abierta = False

    def marcar_fin_escritura(self):
        """Marca fin de reproducción en el parlante."""
        self._reproduciendo_salida = False
        self._ultimo_fin_salida = time.monotonic()

    def marcar_encolado_salida(self):
        """Actualiza marca temporal al recibir nuevo audio de salida."""
        self._ultimo_fin_salida = time.monotonic()
        self._abierta = False

    def esta_en_ventana_eco(self) -> bool:
        """Devuelve True si está reproduciendo o dentro de la ventana de gracia."""
        if self.modo_audifonos:
            return False
        if self._reproduciendo_salida:
            return True
        if self.cola_salida is not None and not getattr(self.cola_salida, "empty", lambda: True)():
            return True
        cola_s = self.eco_cola_ms / 1000.0
        return (time.monotonic() - self._ultimo_fin_salida) < cola_s

    def filtrar_chunk_entrada(self, chunk: bytes) -> tuple[bytes, bool]:
        """Si está en ventana eco: devuelve silencio y silenciado=True."""
        if not chunk:
            return b"", False
        if self.esta_en_ventana_eco():
            self._abierta = False
            return bytes(len(chunk)), True
        if not self._abierta:
            self._abierta = True
            print("[LIVE][AUDIO] Compuerta antieco ABIERTA: escuchando usuario.", flush=True)
        return chunk, False

    def registrar_info_inicio(self):
        if self.modo_audifonos:
            print("[LIVE][AUDIO] Compuerta antieco: DESACTIVADA (modo audífonos).", flush=True)
        else:
            print(f"[LIVE][AUDIO] Compuerta antieco: ACTIVA (parlantes, ventana={int(self.eco_cola_ms)}ms).", flush=True)


__all__ = ["CompuertaAntiEco"]
