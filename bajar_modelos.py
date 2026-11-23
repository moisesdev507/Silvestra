r"""Descarga los modelos de la cámara y de voz a la carpeta 'modelos'. Se ejecuta una sola vez:
    .venv\Scripts\python.exe bajar_modelos.py
"""
import os
import sys
import tarfile
import urllib.request
import zipfile

CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modelos")
MODELOS = {
    "face_detection_yunet_2023mar.onnx": [
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    ],
    "face_recognition_sface_2021dec.onnx": [
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    ],
    "hand_landmarker.task": [
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task",
    ],
    "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx": [
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx",
    ],
    "silero_vad.onnx": [
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx",
    ],
}


def bajar(nombre, urls):
    destino = os.path.join(CARPETA, nombre)
    if os.path.exists(destino) and os.path.getsize(destino) > 100_000:
        print("Ya está:", nombre)
        return True
    for url in urls:
        try:
            print("Bajando", nombre, "...")
            urllib.request.urlretrieve(url, destino)
            if os.path.getsize(destino) > 100_000:
                print("  listo (%d KB)" % (os.path.getsize(destino) // 1024))
                return True
            print("  archivo demasiado pequeño, pruebo otra dirección")
        except Exception as e:
            print("  falló:", str(e)[:100])
    return False


KOKORO_URLS = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
    "kokoro-int8-multi-lang-v1_0.tar.bz2",
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
    "kokoro-multi-lang-v1_0.tar.bz2",
)


def bajar_kokoro():
    """Descarga opcional del TTS local Kokoro. No altera los modelos existentes."""
    archivo = os.path.join(CARPETA, "kokoro-int8-multi-lang-v1_0.tar.bz2")
    for url in KOKORO_URLS:
        try:
            if not os.path.exists(archivo) or os.path.getsize(archivo) < 1_000_000:
                print("Bajando modelo Kokoro (TTS local)...")
                urllib.request.urlretrieve(url, archivo)
            with tarfile.open(archivo, "r:bz2") as tar:
                try:
                    tar.extractall(CARPETA, filter="data")
                except TypeError:
                    tar.extractall(CARPETA)
            print("  listo modelo Kokoro")
            if os.path.exists(archivo):
                os.remove(archivo)
            return True
        except Exception as e:
            print(f"  falló Kokoro: {str(e)[:100]}")
    return False


def bajar_vosk():
    nombre_carpeta = "vosk-model-small-es-0.42"
    destino_carpeta = os.path.join(CARPETA, nombre_carpeta)
    if os.path.exists(destino_carpeta) and os.path.isdir(destino_carpeta):
        print("Ya está:", nombre_carpeta)
        return True
    archivo_zip = os.path.join(CARPETA, f"{nombre_carpeta}.zip")
    url = f"https://alphacephei.com/vosk/models/{nombre_carpeta}.zip"
    try:
        if not os.path.exists(archivo_zip) or os.path.getsize(archivo_zip) < 10_000_000:
            print("Bajando modelo Vosk (español)...")
            urllib.request.urlretrieve(url, archivo_zip)
        print("Descomprimiendo modelo Vosk...")
        with zipfile.ZipFile(archivo_zip, "r") as z:
            z.extractall(CARPETA)
        print("  listo modelo Vosk")
        if os.path.exists(archivo_zip):
            try:
                os.remove(archivo_zip)
            except Exception:
                pass
        return True
    except Exception as e:
        print("  falló modelo Vosk:", str(e)[:100])
        return False


if __name__ == "__main__":
    os.makedirs(CARPETA, exist_ok=True)
    todo = all([bajar(n, u) for n, u in MODELOS.items()]) and bajar_vosk()
    if "--kokoro" in sys.argv or os.environ.get("LYRIS_TTS_LOCAL") == "1":
        if not bajar_kokoro():
            print("Kokoro opcional no disponible: se seguirá usando edge-tts.")
    print("\nTodo listo." if todo else "\nFaltó algún archivo. Mándame lo que salió arriba.")
