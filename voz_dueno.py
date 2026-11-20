"""Reconocimiento y verificación del dueño por voz (speaker verification) local y gratis.

Utiliza el modelo CAM++ (3D-Speaker / WeSpeaker) mediante sherpa-onnx en modo ONNX ligero,
sin PyTorch. Carga perezosa del modelo, similitud coseno y política fail-open.
"""
import os
import random
import threading
import time
import numpy as np

import acciones
import estado

BASE = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_VOZ = os.path.join(BASE, "voz_dueno.npy")
MODELO_ONNX = os.path.join(BASE, "modelos", "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx")

_extractor = None
_lock_extractor = threading.Lock()

FRASES_NEGATIVA = [
    "Eso solo se lo hago a Moisés, pero me da gusto escucharte.",
    "Esa orden solo se la obedezco a Moisés. Pero podemos seguir conversando.",
    "Solo le hago caso a mi creador para las cosas de la casa, pero me alegra hablar contigo.",
    "Me caes bien, pero esa acción está reservada solo para Moisés.",
]


def obtener_extractor():
    """Carga perezosa del extractor CAM++ para no subir la RAM ni ralentizar el arranque."""
    global _extractor
    with _lock_extractor:
        if _extractor is None:
            if not os.path.exists(MODELO_ONNX):
                raise RuntimeError(f"No se encontró el modelo de voz en {MODELO_ONNX}. Ejecuta bajar_modelos.py")
            import sherpa_onnx
            config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=MODELO_ONNX,
                num_threads=2,
                provider="cpu",
            )
            _extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)
            print("[voz_dueno] Extractor CAM++ de sherpa-onnx cargado con éxito.", flush=True)
        return _extractor


def extraer_embedding(audio, samplerate=16000):
    """Calcula el vector de embedding de 192 dimensiones a partir de un array de audio int16 o float32."""
    ext = obtener_extractor()
    stream = ext.create_stream()

    # Convertir a arreglo 1D contiguo de float32
    audio_arr = np.asarray(audio, dtype=np.float32)
    if audio_arr.ndim > 1:
        audio_arr = audio_arr[:, 0]  # Si viene con varios canales, usa el primero
    audio_1d = np.ascontiguousarray(audio_arr.reshape(-1), dtype=np.float32)

    # Si los valores están en escala int16 (amplitud máxima > 1.0), normalizar dividiendo por 32768.0
    if len(audio_1d) > 0 and np.abs(audio_1d).max() > 1.0:
        audio_1d = audio_1d / 32768.0

    stream.accept_waveform(samplerate, audio_1d)
    stream.input_finished()
    emb = ext.compute(stream)
    emb_arr = np.array(emb, dtype=np.float32)
    norm = np.linalg.norm(emb_arr)
    if norm > 1e-6:
        emb_arr /= norm
    return emb_arr


def calcular_similitud(emb1, emb2):
    """Calcula la similitud coseno entre dos vectores normalizados."""
    return float(np.dot(emb1, emb2))


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


class VozDueno:
    """Controlador de verificación de voz del dueño y autorización de acciones."""

    def __init__(self, app):
        self.app = app
        self.vector_dueno = None
        self.activa = False
        self.umbral = 0.42
        self.modo_solo_dueno = False
        self.ultima_verificacion = {"es_dueno": True, "similitud": 1.0, "motivo": "inicial"}
        self._cargar_configuracion()
        self._cargar_vector()

    def _cargar_configuracion(self):
        try:
            datos = estado.cargar()
            self.activa = bool(datos.get("verificacion_voz_activa", False))
            self.umbral = float(datos.get("umbral_voz_dueno", 0.42))
            self.modo_solo_dueno = bool(datos.get("modo_solo_dueno", False))
        except Exception:
            self.activa = False
            self.umbral = 0.42
            self.modo_solo_dueno = False

    def _cargar_vector(self):
        try:
            if os.path.exists(ARCHIVO_VOZ):
                vec = np.load(ARCHIVO_VOZ).astype(np.float32)
                norm = np.linalg.norm(vec)
                if norm > 1e-6:
                    vec /= norm
                self.vector_dueno = vec
            else:
                self.vector_dueno = None
        except Exception as e:
            print(f"[voz_dueno] Error cargando vector biométrico: {e}", flush=True)
            self.vector_dueno = None

    def recargar_vector(self):
        """Vuelve a cargar el vector del dueño tras un registro o calibración."""
        self._cargar_vector()
        self._cargar_configuracion()

    def evaluar_entrada_voz(self, texto):
        """Evalúa la identidad del hablante al recibir un audio del micrófono."""
        if not self.activa or self.vector_dueno is None:
            self.ultima_verificacion = {"es_dueno": True, "similitud": 1.0, "motivo": "inactivo"}
            return

        audio = getattr(self.app.oido, "ultimo_audio", None)
        duracion = float(getattr(self.app.oido, "duracion_ultimo_audio", 0.0))

        # Doble factor con cámara
        camara_ok = bool(
            hasattr(self.app, "camara")
            and self.app.camara
            and self.app.camara.activa
            and self.app.camara.permite()
        )

        # Audios muy cortos (< 1 segundo): decide la cámara; si no hay cámara, no permite acciones
        if audio is None or duracion < 1.0:
            es_dueno = camara_ok
            self.ultima_verificacion = {
                "es_dueno": es_dueno,
                "similitud": 0.0,
                "camara": camara_ok,
                "motivo": "audio_corto_camara_ok" if camara_ok else "audio_corto_sin_camara",
            }
            print(f"[voz_dueno] audio_corto={duracion:.2f}s camara_ok={camara_ok} permitido={es_dueno}", flush=True)
            return

        try:
            audio_limpio = filtrar_voz_activa(audio)
            dur_filtrada = len(audio_limpio) / 16000.0 if audio_limpio is not None else duracion
            emb = extraer_embedding(audio_limpio)
            sim = calcular_similitud(emb, self.vector_dueno)

            # Tolerancia en clips cortos del dueño (0.8s a 1.8s) con pocos fonemas
            umbral_efectivo = self.umbral
            if 0.8 <= dur_filtrada <= 1.8:
                umbral_efectivo = max(0.38, self.umbral - 0.03)

            # Log exacto: [voz_dueno] similitud=0.xx umbral=0.xx duracion=X.XXs filtrado=X.XXs camara=True/False
            print(f"[voz_dueno] similitud={sim:.2f} umbral={self.umbral:.2f} duracion={duracion:.2f}s filtrado={dur_filtrada:.2f}s camara={camara_ok}", flush=True)

            # Doble factor: si la cámara ve al dueño, es válido aunque el puntaje de voz sea bajo
            es_dueno = (sim >= umbral_efectivo) or camara_ok
            self.ultima_verificacion = {
                "es_dueno": es_dueno,
                "similitud": sim,
                "camara": camara_ok,
                "motivo": "camara" if (camara_ok and sim < self.umbral) else ("voz_ok" if es_dueno else "rechazado"),
            }
        except Exception as e:
            # Política fail-open: nunca dejar fuera al dueño ante fallos técnicos
            print(f"[voz_dueno] Error al verificar voz (fail-open activado): {e}", flush=True)
            self.ultima_verificacion = {"es_dueno": True, "similitud": 1.0, "motivo": "error_tolerado"}

    def autorizar_accion(self, accion):
        """Decide si una acción solicitada se ejecuta o se bloquea con una frase amable."""
        origen = getattr(self.app, "origen_entrada_actual", "chat")
        # Chat en laptop y Telegram emparejado siempre se aceptan
        if origen in ("chat", "telegram"):
            return True, ""

        if not self.activa or self.vector_dueno is None:
            return True, ""

        if self.ultima_verificacion.get("es_dueno", True):
            return True, ""

        # Rechazo con gracia para acciones sensibles
        frase = random.choice(FRASES_NEGATIVA)
        sim = self.ultima_verificacion.get("similitud", 0.0)
        print(f"[voz_dueno] Acción '{accion}' bloqueada. Similitud={sim:.2f} < Umbral={self.umbral:.2f}", flush=True)
        return False, frase

    def activar(self):
        """Activa la verificación de voz del dueño."""
        if not os.path.exists(ARCHIVO_VOZ) or self.vector_dueno is None:
            self.app.decir("Aún no has registrado tu voz. Di 'registrar mi voz' para calibrarla primero.")
            return
        self.activa = True
        datos = estado.cargar()
        datos["verificacion_voz_activa"] = True
        estado.guardar(datos)
        print("[voz_dueno] Verificación de voz activada.", flush=True)
        self.app.decir("Verificación de voz activada. A partir de ahora solo obedeceré tus órdenes.")

    def desactivar(self):
        """Desactiva la verificación de voz del dueño."""
        self.activa = False
        datos = estado.cargar()
        datos["verificacion_voz_activa"] = False
        estado.guardar(datos)
        print("[voz_dueno] Verificación de voz desactivada.", flush=True)
        self.app.decir("Verificación de voz desactivada. Responderé a cualquiera que me hable.")

    def activar_modo_solo_dueno(self):
        """Activa el modo exclusivo solo dueño para ignorar por completo a invitados."""
        self.modo_solo_dueno = True
        datos = estado.cargar()
        datos["modo_solo_dueno"] = True
        estado.guardar(datos)
        print("[voz_dueno] Modo solo dueño activado.", flush=True)
        self.app.decir("Modo solo dueño activado. Ignoraré las voces que no sean la tuya.")

    def desactivar_modo_solo_dueno(self):
        """Desactiva el modo exclusivo solo dueño permitiendo hablar con invitados."""
        self.modo_solo_dueno = False
        datos = estado.cargar()
        datos["modo_solo_dueno"] = False
        estado.guardar(datos)
        print("[voz_dueno] Modo solo dueño desactivado.", flush=True)
        self.app.decir("Modo solo dueño desactivado. Responderé amablemente a invitados.")


def instalar(app):
    """Instala el subsistema de voz del dueño y registra sus acciones."""
    import voz_dueno_registro

    vd = VozDueno(app)
    app.voz_dueno = vd

    acciones.registrar(
        "registrar_mi_voz",
        lambda: voz_dueno_registro.iniciar_registro(app, vd),
        "Guía a Moisés para registrar su voz leyendo 6 frases cortas para reconocimiento biométrico.",
    )
    acciones.registrar(
        "calibrar_voz",
        lambda: voz_dueno_registro.iniciar_calibracion(app, vd),
        "Calibra el umbral de verificación comparando frases de Moisés con frases de otra persona.",
    )
    acciones.registrar(
        "activar_verificacion_voz",
        vd.activar,
        "Activa la verificación biométrica de voz para que Silvestra solo obedezca a su dueño.",
    )
    acciones.registrar(
        "desactivar_verificacion_voz",
        vd.desactivar,
        "Desactiva la verificación biométrica de voz permitiendo órdenes de cualquier persona.",
    )
    acciones.registrar(
        "activar_modo_solo_dueno",
        vd.activar_modo_solo_dueno,
        "Activa el modo solo dueño para ignorar por completo voces no identificadas.",
    )
    acciones.registrar(
        "desactivar_modo_solo_dueno",
        vd.desactivar_modo_solo_dueno,
        "Desactiva el modo solo dueño permitiendo que Silvestra hable con invitados.",
    )
    print("[voz_dueno] Módulo instalado correctamente.", flush=True)
