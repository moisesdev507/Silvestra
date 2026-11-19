"""Cámara de Silvestra: reconoce a su dueño y entiende gestos de mano."""
import collections
import os
import threading
import time

import acciones

BASE = os.path.dirname(os.path.abspath(__file__))
RUTA = os.path.join(BASE, "modelos")
ARCHIVO_DUENO = os.path.join(BASE, "dueno.npy")
M_DETECTOR = "face_detection_yunet_2023mar.onnx"
M_RECONOCER = "face_recognition_sface_2021dec.onnx"
M_MANOS = "hand_landmarker.task"

AUTO_ACTIVAR = False  # True = la cámara se enciende sola al abrir Silvestra

# Qué hace cada gesto
GESTOS = {
    "palma": "encender_luz",
    "puno": "apagar_luz",
    "paz": "encender_ventilador",
    "uno": "apagar_ventilador",
}
NOMBRES = {"palma": "palma abierta", "puno": "puño", "paz": "dos dedos", "uno": "un dedo"}


def clasificar(pts):
    """pts: 21 puntos de la mano (con .x y .y). Mano derecha, dedos hacia arriba."""
    arriba = []
    for punta, base in ((8, 6), (12, 10), (16, 14), (20, 18)):
        arriba.append(pts[punta].y < pts[base].y - 0.02)
    indice, medio, anular, menique = arriba
    if all(arriba):
        return "palma"
    if not any(arriba):
        return "puno"
    if indice and medio and not anular and not menique:
        return "paz"
    if indice and not medio and not anular and not menique:
        return "uno"
    return None


class Camara:
    def __init__(self, app):
        self.app = app
        self.activa = False
        self.ultimo_frame = None
        self.eventos = collections.deque()
        self.dueno = None
        self.enrolando = None
        self.enrol_inicio = 0.0
        self.ult_dueno = 0.0
        self.ult_ajeno = 0.0
        self.ult_aviso = 0.0
        self.ult_negativa = 0.0
        self.consecutivos_ajeno = 0
        self.ult_aviso_invitado = 0.0
        self.ult_rostro = 0.0
        self.ult_pos_rostro = None
        self.t_ult_pos_rostro = 0.0
        self._generando_saludo = False
        self._cargar_dueno()

    # ---------- Dueño ----------
    def _cargar_dueno(self):
        try:
            import numpy as np

            if os.path.exists(ARCHIVO_DUENO):
                self.dueno = np.load(ARCHIVO_DUENO).astype("float32")
        except Exception:
            self.dueno = None

    def permite(self):
        """¿Puede obedecer ahora? No, solo si ve a un desconocido y no a su dueño."""
        if not self.activa or self.dueno is None:
            return True
        ahora = time.time()
        if ahora - self.ult_dueno < 6:
            return True
        return not (ahora - self.ult_ajeno < 3)

    # ---------- Órdenes ----------
    def activar(self):
        if self.activa:
            return
        self.activa = True
        threading.Thread(target=self._bucle, daemon=True).start()

    def apagar(self):
        self.activa = False

    def aprender_cara(self):
        if not self.activa:
            self.activar()
        self.enrolando = []
        self.enrol_inicio = time.time()

    def _evento(self, tipo, dato=None):
        self.eventos.append((tipo, dato))

    # ---------- Hilo de la cámara ----------
    def _bucle(self):
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks import python as mpp
            from mediapipe.tasks.python import vision

            detector = cv2.FaceDetectorYN.create(os.path.join(RUTA, M_DETECTOR), "", (320, 320), 0.8, 0.3, 5000)
            reco = cv2.FaceRecognizerSF.create(os.path.join(RUTA, M_RECONOCER), "")
            opciones = vision.HandLandmarkerOptions(
                base_options=mpp.BaseOptions(model_asset_path=os.path.join(RUTA, M_MANOS)),
                num_hands=1,
            )
            manos = vision.HandLandmarker.create_from_options(opciones)
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                raise RuntimeError("No pude abrir la cámara.")
        except Exception as e:
            self.activa = False
            self._evento("error", "No pude encender la cámara: " + str(e)[:120])
            return

        ultimo_rostro = 0.0
        gesto = {"g": None, "n": 0, "t": 0.0}
        fallos = 0
        try:
            while self.activa:
                try:
                    ok, frame = cap.read()
                    if not ok:
                        time.sleep(0.1)
                        continue
                    frame = cv2.flip(frame, 1)
                    self.ultimo_frame = frame
                    ahora = time.time()
                    intervalo = 0.3 if self.enrolando is not None else 0.6
                    if ahora - ultimo_rostro > intervalo:
                        ultimo_rostro = ahora
                        self._rostros(cv2, detector, reco, frame)
                    self._manos(cv2, mp, manos, frame, gesto)
                    fallos = 0
                except Exception as e:
                    fallos += 1
                    if fallos > 20:
                        self.activa = False
                        self._evento("error", "La cámara falló: " + str(e)[:100])
                time.sleep(0.04)
        finally:
            try:
                cap.release()
            except Exception:
                pass

    def _rostros(self, cv2, detector, reco, frame):
        import numpy as np

        alto, ancho = frame.shape[:2]
        detector.setInputSize((ancho, alto))
        _, caras = detector.detect(frame)
        ahora = time.time()
        if self.enrolando is not None and ahora - self.enrol_inicio > 25:
            self.enrolando = None
            self._evento("error", "No logré verte bien. Mírame de frente con buena luz e inténtalo otra vez.")
            return
        if caras is None:
            self.consecutivos_ajeno = 0
            return
        caras = sorted(caras, key=lambda c: -c[2] * c[3])[:3]
        self.ult_rostro = ahora
        if len(caras) > 0:
            c0 = caras[0]
            cx = (c0[0] + c0[2] / 2.0) / float(ancho)
            cy = (c0[1] + c0[3] / 2.0) / float(alto)
            self.ult_pos_rostro = (cx * 2.0 - 1.0, cy * 2.0 - 1.0)
            self.t_ult_pos_rostro = ahora
        vio_dueno = False
        vio_ajeno = False
        for cara in caras:
            feat = reco.feature(reco.alignCrop(frame, cara))
            if self.enrolando is not None:
                self.enrolando.append(feat.copy())
                if len(self.enrolando) >= 8:
                    media = np.mean(np.vstack(self.enrolando), axis=0, keepdims=True).astype("float32")
                    np.save(ARCHIVO_DUENO, media)
                    self.dueno = media
                    self.enrolando = None
                    self.ult_dueno = ahora
                    self._evento("aprendida")
                return
            if self.dueno is None:
                return
            if reco.match(self.dueno, feat, cv2.FaceRecognizerSF_FR_COSINE) >= 0.363:
                vio_dueno = True
                if ahora - self.ult_dueno > 120:
                    self._evento("saludo")
                self.ult_dueno = ahora
            else:
                vio_ajeno = True

        if vio_dueno:
            self.consecutivos_ajeno = 0
        elif vio_ajeno:
            self.ult_ajeno = ahora
            self.consecutivos_ajeno += 1
            # Requiere permanencia estable (>= 3 detecciones consecutivas ~1.8 s) y 2 min de cooldown
            if self.consecutivos_ajeno >= 3 and (ahora - self.ult_aviso_invitado > 120) and (ahora - self.ult_dueno > 6):
                self.ult_aviso_invitado = ahora
                self.consecutivos_ajeno = 0
                self._evento("invitado")
        else:
            self.consecutivos_ajeno = 0

    def _manos(self, cv2, mp, manos, frame, estado):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        imagen = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res = manos.detect(imagen)
        g = clasificar(res.hand_landmarks[0]) if res.hand_landmarks else None
        if g and g == estado["g"]:
            estado["n"] += 1
        else:
            estado["g"] = g
            estado["n"] = 1 if g else 0
        ahora = time.time()
        if g and estado["n"] >= 6 and ahora - estado["t"] > 2.5:
            estado["t"] = ahora
            estado["n"] = 0
            self._evento("gesto", g)

    # ---------- Hilo principal ----------
    def _voz_ocupada(self):
        try:
            return self.app.voz.ocupada()
        except Exception:
            return False

    def revisar(self):
        while self.eventos:
            if self.eventos[0][0] != "gesto" and not self.app.puede_hablar_sola():
                break  # espera a que pueda hablar sola para no pisarse ni interrumpir
            tipo, dato = self.eventos.popleft()
            if self.app.descansando:
                continue
            if tipo == "error":
                self.app.decir(dato, 5000)
            elif tipo == "aprendida":
                self.app.decir(f"Listo, ya me aprendí tu cara, {self.app.memoria.creador}.", 3500)
            elif tipo == "saludo":
                self.app.decir(f"Hola, {self.app.memoria.creador}.", 3000)
            elif tipo == "invitado":
                if not self._generando_saludo:
                    self._generando_saludo = True
                    threading.Thread(target=self._generar_saludo_invitado, daemon=True).start()
            elif tipo == "desconocido":
                self.app.decir("Hola. No te conozco. Yo solo obedezco a mi dueño.", 4000)
            elif tipo == "gesto":
                self._gesto(dato)
        self.app.cara.root.after(200, self.revisar)

    def _generar_saludo_invitado(self):
        """Genera un saludo cálido e improvisado con el cerebro cuando se detecta un invitado."""
        try:
            nombre_creador = getattr(self.app.memoria, "creador", "Moisés")
            nombre_asistente = getattr(self.app.memoria, "nombre", "Silvestra")
            respaldo = f"Hola, veo que eres un invitado. Yo solo recibo órdenes de {nombre_creador}, pero me da gusto saludarte."
            sistema = (
                f"Eres {nombre_asistente}, asistente de {nombre_creador} en Panamá. "
                f"La cámara detectó a un invitado, profesor o compañero de clase que no es {nombre_creador}. "
                "Salúdalo con una frase corta, natural, amable y respetuosa (1 o 2 frases cortas, máximo 20 palabras). "
                f"Debes mencionar que reconoces que es un invitado, que solo recibes órdenes de {nombre_creador}, "
                "y que te da gusto saludarlo. En español panameño natural, sin asteriscos, sin listas y sin comillas."
            )
            frase = self.app.cerebro._pedir([
                {"role": "system", "content": sistema},
                {"role": "user", "content": "Saluda brevemente al invitado frente a la cámara."}
            ])
            frase = frase.replace("*", "").replace('"', '').replace("\n", " ").strip()
            if not frase or len(frase) < 10:
                frase = respaldo
        except Exception:
            frase = f"Hola, veo que eres un invitado. Yo solo recibo órdenes de {getattr(self.app.memoria, 'creador', 'Moisés')}, pero me da gusto saludarte."
        finally:
            self._generando_saludo = False
        if hasattr(self.app, "cola"):
            self.app.cola.put(("saludo_invitado", frase))

    def _gesto(self, g):
        accion = GESTOS.get(g)
        if not accion:
            return
        if not self.permite():
            if time.time() - self.ult_negativa > 10:
                self.ult_negativa = time.time()
                self.app.decir("Solo obedezco a mi dueño.", 3000)
            return
        self.app.cara.decir("Gesto: " + NOMBRES[g], 1800)
        if hasattr(self.app, "cola"):
            self.app.cola.put(("escenario_gesto", (g, accion, NOMBRES.get(g, g), False)))
        acciones.ejecutar(accion)


    def capturar_fotograma(self):
        """Devuelve un fotograma (numpy array en formato BGR) de la cámara.
        Si la cámara ya está activa por reconocimiento, reutiliza el último fotograma.
        Si está apagada, la abre brevemente, captura un fotograma y la apaga."""
        if self.activa and self.ultimo_frame is not None:
            return self.ultimo_frame.copy()

        try:
            import cv2
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                return None
            try:
                frame = None
                for _ in range(3):
                    ok, f = cap.read()
                    if ok and f is not None:
                        frame = f
                if frame is not None:
                    return cv2.flip(frame, 1)
            finally:
                cap.release()
        except Exception as e:
            print(f"[camara] Error capturando fotograma: {e}", flush=True)
            return None
        return None


def instalar(app):
    cam = Camara(app)
    acciones.registrar("activar_camara", cam.activar, "enciende la cámara para ver gestos de la mano y reconocer a su dueño")
    acciones.registrar("apagar_camara", cam.apagar, "apaga la cámara")
    acciones.registrar(
        "aprender_mi_cara",
        cam.aprender_cara,
        "aprende la cara de su dueño con la cámara (dile que te mire de frente unos segundos)",
    )
    app.cara.root.after(300, cam.revisar)
    if AUTO_ACTIVAR:
        app.cara.root.after(1500, cam.activar)
    return cam