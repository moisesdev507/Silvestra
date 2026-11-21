"""Comparador local y acotado de fotogramas."""
from __future__ import annotations

import hashlib
import threading

from camara_percepcion_modelo import ResultadoComparacionFrame


class ComparadorFotogramas:
    def __init__(self, ancho=160, alto=120) -> None:
        self.ancho = max(16, int(ancho))
        self.alto = max(16, int(alto))
        self._bloqueo = threading.RLock()
        self._previo = None

    def _miniatura(self, frame):
        try:
            if hasattr(frame, "convert"):
                img = frame.convert("RGB")
                img = img.resize((self.ancho, self.alto))
                gris = img.convert("L")
                arr = __import__("numpy").asarray(gris, dtype="uint8")
                try:
                    gris.close()
                except Exception:
                    pass
                try:
                    img.close()
                except Exception:
                    pass
                return arr
            import numpy as np
            arr = np.asarray(frame)
            if arr is None or arr.size == 0:
                return None
            if arr.ndim == 3:
                if arr.shape[2] >= 3:
                    gris = (
                        arr[:, :, 0].astype("int16") * 299
                        + arr[:, :, 1].astype("int16") * 587
                        + arr[:, :, 2].astype("int16") * 114
                    ) // 1000
                    arr = gris.astype("uint8")
                else:
                    arr = arr[:, :, 0]
            if arr.ndim != 2:
                return None
            try:
                import cv2
                arr = cv2.resize(
                    arr,
                    (self.ancho, self.alto),
                    interpolation=cv2.INTER_AREA,
                )
            except Exception:
                from PIL import Image
                import numpy as np
                arr = np.asarray(
                    Image.fromarray(arr).resize((self.ancho, self.alto))
                )
            return arr.astype("uint8")
        except Exception:
            return None

    def comparar(self, frame, umbral=0.12) -> ResultadoComparacionFrame:
        arr = self._miniatura(frame)
        if arr is None:
            return ResultadoComparacionFrame(
                1.0, True, True, anomalia_sensor="frame_invalido"
            )
        huella = hashlib.sha256(arr.tobytes()).hexdigest()
        with self._bloqueo:
            previo = self._previo
            if previo is not None and huella == previo["huella"]:
                return ResultadoComparacionFrame(
                    0.0, False, False,
                    anomalia_sensor=previo["anomalia"],
                    huella_frame=huella,
                )
            if previo is None:
                dif = 0.0
            else:
                dif_arr = abs(arr.astype("int16") - previo["arr"].astype("int16"))
                dif = float(dif_arr.mean() / 255.0)

            anomalia = None
            if float(arr.mean()) < 3.0:
                anomalia = "camara_ocluida_o_negra"
            elif float(arr.std()) < 2.0:
                anomalia = "camara_baja_variacion"

            regiones = []
            if previo is not None and dif >= umbral:
                import numpy as np
                mascara = abs(
                    arr.astype("int16") - previo["arr"].astype("int16")
                ) > 24
                ys, xs = np.where(mascara)
                if len(xs):
                    regiones.append((
                        int(xs.min()), int(ys.min()),
                        int(xs.max()), int(ys.max()),
                    ))
            self._previo = {
                "arr": arr.copy(),
                "huella": huella,
                "anomalia": anomalia,
            }
        return ResultadoComparacionFrame(
            dif,
            dif >= umbral,
            dif >= umbral,
            regiones_movimiento=regiones,
            anomalia_sensor=anomalia,
            huella_frame=huella,
        )

    def reiniciar(self) -> None:
        with self._bloqueo:
            self._previo = None
