"""Banco biométrico multi-muestra y preprocesamiento unificado para verificación de voz.

Gestiona almacenamiento (N, 192), similitud multi-muestra (top-2 para N >= 3),
rotación FIFO con preservación de 8 muestras base y preprocesamiento idéntico (VAD + normalización).
"""
import os
import numpy as np

MAX_MUESTRAS = 25
MUESTRAS_BASE_PRESERVADAS = 8


def filtrar_voz_activa(audio, samplerate=16000):
    """Filtra silencios y tramos muertos antes de CAM++ para optimizar precisión y velocidad.

    Conserva ventanas con voz activa según RMS dinámico con padding de bordes y
    recorta a máximo 6 s. Si la voz activa resultante es menor a 0.8 s, usa el audio original.
    """
    if audio is None:
        return None

    arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr[:, 0]
    total_muestras = len(arr)

    tam_ventana = int(samplerate * 0.030)  # 30 ms (480 muestras)
    if total_muestras < tam_ventana * 4:
        return audio

    num_ventanas = total_muestras // tam_ventana
    recortado = arr[: num_ventanas * tam_ventana].reshape((num_ventanas, tam_ventana))

    # Energía RMS por ventana
    rms_ventanas = np.sqrt(np.mean(recortado ** 2, axis=1))
    piso_ruido = float(np.percentile(rms_ventanas, 25))
    rms_max = float(np.max(rms_ventanas))

    if rms_max <= 1e-4:
        return audio

    if piso_ruido >= rms_max * 0.75:
        activa = np.ones(num_ventanas, dtype=bool)
    else:
        umbral = max(piso_ruido * 1.5, piso_ruido + (rms_max - piso_ruido) * 0.10)
        activa = rms_ventanas >= umbral

    duracion_total = total_muestras / float(samplerate)
    pad_ventanas = 2 if duracion_total <= 2.2 else 1
    activa_pad = activa.copy()
    for i in range(num_ventanas):
        if activa[i]:
            for p in range(1, pad_ventanas + 1):
                if i - p >= 0:
                    activa_pad[i - p] = True
                if i + p < num_ventanas:
                    activa_pad[i + p] = True

    indices_activos = np.where(activa_pad)[0]
    duracion_activa = len(indices_activos) * 0.030

    # Fallback a audio original si queda menos de 0.8 segundos de voz real
    if duracion_activa < 0.8:
        return audio

    # Recortar a máximo 6 segundos de voz activa más fuerte
    max_ventanas = int(6.0 / 0.030)  # 200 ventanas
    if len(indices_activos) > max_ventanas:
        ventanas_filtradas = recortado[indices_activos]
        rms_filtradas = rms_ventanas[indices_activos]
        suma_movil = np.convolve(rms_filtradas, np.ones(max_ventanas), mode="valid")
        mejor_inicio = int(np.argmax(suma_movil))
        ventanas_sel = ventanas_filtradas[mejor_inicio : mejor_inicio + max_ventanas]
        audio_filtrado = ventanas_sel.reshape(-1)
    else:
        audio_filtrado = recortado[indices_activos].reshape(-1)

    if isinstance(audio, np.ndarray) and audio.dtype == np.int16:
        return np.clip(audio_filtrado, -32768, 32767).astype(np.int16)
    return audio_filtrado


def preparar_audio_biometria(audio, samplerate=16000):
    """Aplica preprocesamiento uniforme a señales de audio tanto en registro como en vivo:
    conversión float32 1D, remoción de offset DC, normalización de pico a ~-3 dBFS y VAD.

    Retorna (audio_limpio, duracion_filtrada_segundos).
    """
    if audio is None:
        return None, 0.0

    audio_f = np.asarray(audio, dtype=np.float32)
    if audio_f.ndim > 1:
        audio_f = audio_f[:, 0]
    audio_f = audio_f.reshape(-1)

    if len(audio_f) == 0:
        return np.array([], dtype=np.int16), 0.0

    # 1. Remoción de offset DC
    audio_f = audio_f - float(np.mean(audio_f))

    # 2. Normalización de pico a ~-3 dBFS (24000/32768)
    max_v = float(np.max(np.abs(audio_f)))
    if max_v > 50.0:
        escala = min(3.5, 24000.0 / max_v)
        audio_f = audio_f * escala

    audio_int16 = np.clip(audio_f, -32767, 32767).astype(np.int16)

    # 3. Filtrado de silencios VAD
    audio_limpio = filtrar_voz_activa(audio_int16, samplerate)
    if audio_limpio is None:
        return None, 0.0

    duracion = len(audio_limpio) / float(samplerate)
    return audio_limpio, duracion


def cargar_banco(ruta):
    """Carga el banco biométrico desde un archivo .npy.

    Soporta compatibilidad retroactiva con vectores 1D (192,) convirtiéndolos a matriz (1, 192).
    Retorna una matriz float32 2D (N, 192) con filas normalizadas L2, o None si no existe o es inválido.
    """
    if not os.path.exists(ruta):
        return None
    try:
        data = np.load(ruta).astype(np.float32)
        if data.ndim == 1:
            if len(data) != 192:
                return None
            data = data.reshape(1, -1)
        elif data.ndim == 2:
            if data.shape[1] != 192:
                return None
        else:
            return None

        # Normalizar L2 cada fila
        normas = np.linalg.norm(data, axis=1, keepdims=True)
        normas = np.where(normas > 1e-6, normas, 1.0)
        data = data / normas
        return data.astype(np.float32)
    except Exception as e:
        print(f"[voz_dueno_banco] Error cargando banco desde {ruta}: {e}", flush=True)
        return None


def guardar_banco(ruta, banco):
    """Guarda una matriz 2D (N, 192) en ruta normalizando cada fila L2."""
    if banco is None or len(banco) == 0:
        return
    data = np.asarray(banco, dtype=np.float32)
    if data.ndim == 1:
        data = data.reshape(1, -1)
    normas = np.linalg.norm(data, axis=1, keepdims=True)
    normas = np.where(normas > 1e-6, normas, 1.0)
    data = data / normas
    np.save(ruta, data.astype(np.float32))


def calcular_similitud_banco(emb, banco):
    """Calcula la similitud de un embedding contra el banco biométrico.

    Retorna una tupla (score, max_sim, n_muestras).
    Si n >= 3, score es el promedio de las 2 mejores similitudes.
    Si n < 3, score es la máxima similitud.
    """
    if emb is None or banco is None or len(banco) == 0:
        return 0.0, 0.0, 0

    emb_1d = np.asarray(emb, dtype=np.float32).reshape(-1)
    norm = np.linalg.norm(emb_1d)
    if norm > 1e-6:
        emb_1d = emb_1d / norm

    sims = np.dot(banco, emb_1d)
    n = len(sims)
    max_sim = float(np.max(sims))

    if n >= 3:
        top2 = np.sort(sims)[-2:]
        score = float(np.mean(top2))
    else:
        score = max_sim

    return score, max_sim, n


def agregar_muestra_banco(emb, banco, max_muestras=MAX_MUESTRAS):
    """Añade un embedding normalizado al banco biométrico.

    - Omite la muestra si tiene similitud > 0.96 con alguna existente.
    - Si len(banco) < max_muestras, añade al final.
    - Si len(banco) >= max_muestras, mantiene las 8 primeras muestras base
      y rota las restantes en FIFO (descarta la fila 8 y agrega la nueva).

    Retorna (nuevo_banco, True) si se agregó, o (banco, False) si fue omitida.
    """
    if emb is None:
        return banco, False

    emb_1d = np.asarray(emb, dtype=np.float32).reshape(-1)
    if len(emb_1d) != 192:
        return banco, False

    norm = np.linalg.norm(emb_1d)
    if norm > 1e-6:
        emb_1d = emb_1d / norm
    nueva_fila = emb_1d.reshape(1, -1)

    if banco is None or len(banco) == 0:
        return nueva_fila.copy(), True

    banco_arr = np.asarray(banco, dtype=np.float32)
    sims = np.dot(banco_arr, emb_1d)
    if float(np.max(sims)) > 0.96:
        return banco_arr, False

    if len(banco_arr) < max_muestras:
        nuevo_banco = np.vstack([banco_arr, nueva_fila])
        return nuevo_banco, True

    # Rotación FIFO preservando las 8 primeras muestras base (0..7)
    base = banco_arr[:MUESTRAS_BASE_PRESERVADAS]
    dinamicas = banco_arr[MUESTRAS_BASE_PRESERVADAS + 1 :]
    nuevo_banco = np.vstack([base, dinamicas, nueva_fila])
    return nuevo_banco, True
