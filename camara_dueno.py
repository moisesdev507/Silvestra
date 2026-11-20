"""Gestión de banco biométrico facial multi-muestra con SFace y YuNet.

Permite almacenar hasta MAX_MUESTRAS_CARA en dueno.npy con scoring multi-muestra (top-2),
rotación FIFO de muestras dinámicas (preservando anclas base) y aprendizaje de fotos desde Telegram o webcam.
"""
import os
import unicodedata
import cv2
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
RUTA_MODELOS = os.path.join(BASE, "modelos")
RUTA_YUNET = os.path.join(RUTA_MODELOS, "face_detection_yunet_2023mar.onnx")
RUTA_SFACE = os.path.join(RUTA_MODELOS, "face_recognition_sface_2021dec.onnx")
ARCHIVO_DUENO = os.path.join(BASE, "dueno.npy")

MAX_MUESTRAS_CARA = 20
MUESTRAS_BASE_PRESERVADAS = 4

FRASES_ENTRENAMIENTO = (
    "mi cara",
    "entrenar cara",
    "aprender cara",
    "registrar cara",
    "guarda mi cara",
    "esta es mi cara",
    "foto cara",
    "/entrenar_cara",
    "foto de mi cara",
    "guarda mi rostro",
    "mi rostro",
    "entrenar rostro",
    "aprender rostro",
    "registrar rostro",
    "registro de rostro",
    "registro de cara",
    "actualizar mi rostro",
    "actualizar mi cara",
)


def es_foto_entrenamiento_cara(caption):
    """True si el texto del caption contiene una orden de entrenamiento facial."""
    if not caption:
        return False
    t = unicodedata.normalize("NFD", caption.lower())
    texto = "".join(c for c in t if unicodedata.category(c) != "Mn").strip()
    return any(f in texto for f in FRASES_ENTRENAMIENTO)


def normalizar_l2(v):
    """Normaliza un vector o filas de una matriz a norma L2 unitaria."""
    arr = np.asarray(v, dtype=np.float32)
    if arr.ndim == 1:
        norm = float(np.linalg.norm(arr))
        return arr / norm if norm > 1e-6 else arr
    elif arr.ndim == 2:
        normas = np.linalg.norm(arr, axis=1, keepdims=True)
        normas = np.where(normas > 1e-6, normas, 1.0)
        return (arr / normas).astype(np.float32)
    return arr


def cargar_banco_cara(ruta=ARCHIVO_DUENO):
    """Carga el banco facial desde dueno.npy con retrocompatibilidad 1D (128,) a 2D (1, 128)."""
    if not os.path.exists(ruta):
        return None
    try:
        data = np.load(ruta).astype(np.float32)
        if data.ndim == 1:
            if len(data) != 128:
                return None
            data = data.reshape(1, 128)
        elif data.ndim == 2:
            if data.shape[1] != 128:
                return None
        else:
            return None
        return normalizar_l2(data)
    except Exception as e:
        print(f"[camara_dueno] Error cargando banco facial: {e}", flush=True)
        return None


def guardar_banco_cara(banco, ruta=ARCHIVO_DUENO):
    """Guarda la matriz 2D (N, 128) float32 de forma atómica en disco."""
    if banco is None or len(banco) == 0:
        return False
    data = normalizar_l2(banco)
    if data.ndim == 1:
        data = data.reshape(1, 128)
    base = ruta[:-4] if ruta.endswith(".npy") else ruta
    tmp_ruta = f"{base}_tmp.npy"
    try:
        np.save(tmp_ruta, data.astype(np.float32))
        os.replace(tmp_ruta, ruta)
        return True
    except Exception as e:
        print(f"[camara_dueno] Error guardando banco de caras: {e}", flush=True)
        if os.path.exists(tmp_ruta):
            try:
                os.remove(tmp_ruta)
            except Exception:
                pass
        return False


def calcular_similitud_cara(emb, banco):
    """Calcula la similitud coseno contra el banco facial.

    Retorna (score, max_sim, n_muestras).
    Si n >= 3, devuelve el promedio de las 2 mayores similitudes; si no, la máxima.
    """
    if emb is None or banco is None or len(banco) == 0:
        return 0.0, 0.0, 0

    emb_1d = normalizar_l2(np.asarray(emb, dtype=np.float32).reshape(-1))
    sims = np.dot(banco, emb_1d)
    n = len(sims)
    max_sim = float(np.max(sims))

    if n >= 3:
        top2 = np.sort(sims)[-2:]
        score = float(np.mean(top2))
    else:
        score = max_sim

    return score, max_sim, n


def agregar_muestra_cara(emb, banco, max_muestras=MAX_MUESTRAS_CARA):
    """Añade un embedding al banco facial evitando duplicados (>0.94) y con rotación FIFO."""
    if emb is None:
        return banco, False

    emb_1d = normalizar_l2(np.asarray(emb, dtype=np.float32).reshape(-1))
    if len(emb_1d) != 128:
        return banco, False
    fila = emb_1d.reshape(1, 128)

    if banco is None or len(banco) == 0:
        return fila.copy(), True

    banco_arr = normalizar_l2(banco)
    sims = np.dot(banco_arr, emb_1d)
    if float(np.max(sims)) > 0.94:
        return banco_arr, False

    if len(banco_arr) < max_muestras:
        return np.vstack([banco_arr, fila]), True

    # Rotación FIFO preservando las primeras MUESTRAS_BASE_PRESERVADAS (índices 0..3)
    base = banco_arr[:MUESTRAS_BASE_PRESERVADAS]
    dinamicas = banco_arr[MUESTRAS_BASE_PRESERVADAS + 1 :]
    nuevo = np.vstack([base, dinamicas, fila])
    return nuevo, True


def aprender_cara_desde_bytes(imagen_bytes, ruta=ARCHIVO_DUENO):
    """Decodifica una imagen, detecta rostros con YuNet y extrae embedding SFace."""
    if not imagen_bytes:
        return False, "No se recibieron datos de imagen.", 0

    nparr = np.frombuffer(imagen_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return False, "No pude decodificar el formato de la foto.", 0

    # Redimensionar fotos de celular manteniendo proporción
    alto, ancho = img.shape[:2]
    max_dim = 1280
    if ancho > max_dim or alto > max_dim:
        esc = min(max_dim / float(ancho), max_dim / float(alto))
        nw = max(1, int(ancho * esc))
        nh = max(1, int(alto * esc))
        img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
        alto, ancho = img.shape[:2]

    if not os.path.exists(RUTA_YUNET) or not os.path.exists(RUTA_SFACE):
        return False, "Faltan los modelos de visión facial (ejecuta bajar_modelos.py).", 0

    detector = cv2.FaceDetectorYN.create(RUTA_YUNET, "", (ancho, alto), 0.7, 0.3, 5000)
    reco = cv2.FaceRecognizerSF.create(RUTA_SFACE, "")
    detector.setInputSize((ancho, alto))
    _, caras = detector.detect(img)

    banco_actual = cargar_banco_cara(ruta)
    n_actual = len(banco_actual) if banco_actual is not None else 0

    if caras is None or len(caras) == 0:
        return False, "No detecté ninguna cara clara en la foto. Intenta con mejor luz y mirando de frente.", n_actual

    if len(caras) > 1:
        return False, "Detecté varias personas en la foto. Mándame una donde salgas solo tú para no mezclar caras.", n_actual

    # Exactamente 1 rostro detectado
    cara = caras[0]
    crop = reco.alignCrop(img, cara)
    feat = reco.feature(crop)
    feat_1d = normalizar_l2(np.asarray(feat, dtype=np.float32).reshape(-1))

    nuevo_banco, agregado = agregar_muestra_cara(feat_1d, banco_actual, max_muestras=MAX_MUESTRAS_CARA)
    if not agregado:
        return False, f"Esa cara ya está registrada en mi banco (similitud muy alta). Tengo {n_actual} muestras tuyas.", n_actual

    guardar_banco_cara(nuevo_banco, ruta)
    n_nuevo = len(nuevo_banco)
    print(f"[camara_dueno] Nueva muestra guardada en {ruta}. Total: {n_nuevo}", flush=True)
    return True, f"Foto aprendida. Ahora tengo {n_nuevo} muestras de tu cara.", n_nuevo
