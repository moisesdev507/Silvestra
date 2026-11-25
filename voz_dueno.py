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
import rutas_app
from voz_dueno_banco import (
    filtrar_voz_activa,
    preparar_audio_biometria,
    cargar_banco,
    guardar_banco,
    calcular_similitud_banco,
    agregar_muestra_banco,
)

ARCHIVO_VOZ = os.path.join(rutas_app.dir_usuario(), "voz_dueno.npy")
MODELO_ONNX = rutas_app.ruta_recurso(
    "modelos", "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx")
GRACIA_DUENO_SEG = 90.0  # ventana de gracia tras verificación biométrica positiva

_extractor = None
_lock_extractor = threading.Lock()

_cache_biometria = {}
_lock_cache = threading.RLock()
TTL_CACHE_SEG = 4.0

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


class VozDueno:
    """Controlador de verificación de voz del dueño y autorización de acciones."""

    def __init__(self, app):
        self.app = app
        self.banco_dueno = None
        self.vector_dueno = None  # Alias para retrocompatibilidad
        self.ultimo_embedding = None
        self.activa = False
        self.umbral = 0.35
        self.modo_solo_dueno = False
        self.ultima_verificacion = {"es_dueno": True, "similitud": 1.0, "motivo": "inicial"}
        self._dueno_verificado_ts = 0.0  # último positivo biométrico (monotónico)
        self._cargar_configuracion()
        self._cargar_vector()

    def _cargar_configuracion(self):
        try:
            datos = estado.cargar()
            self.activa = bool(datos.get("verificacion_voz_activa", False))
            self.umbral = float(datos.get("umbral_voz_dueno", 0.35))
            self.modo_solo_dueno = bool(datos.get("modo_solo_dueno", False))
        except Exception:
            self.activa = False
            self.umbral = 0.35
            self.modo_solo_dueno = False

    def _cargar_vector(self):
        try:
            self.banco_dueno = cargar_banco(ARCHIVO_VOZ)
            self.vector_dueno = self.banco_dueno
        except Exception as e:
            print(f"[voz_dueno] Error cargando banco biométrico: {e}", flush=True)
            self.banco_dueno = None
            self.vector_dueno = None

    def recargar_vector(self):
        """Vuelve a cargar el vector del dueño tras un registro o calibración."""
        self._cargar_vector()
        self._cargar_configuracion()

    def _gracia_dueno_reciente(self):
        """True solo si hubo verificación biométrica positiva dentro de la ventana."""
        ts = float(getattr(self, "_dueno_verificado_ts", 0.0) or 0.0)
        return bool(ts and (time.monotonic() - ts) <= GRACIA_DUENO_SEG)

    def evaluar_entrada_voz(self, texto):
        """Evalúa la identidad del hablante al recibir un audio del micrófono."""
        if not self.activa or self.banco_dueno is None:
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

        # Audios muy cortos (< 1 segundo): decide la cámara o la gracia del dueño
        # verificado hace poco; sin ambas, sigue siendo invitado.
        if audio is None or duracion < 1.0:
            gracia = self._gracia_dueno_reciente()
            es_dueno = camara_ok or gracia
            if not es_dueno:
                self._dueno_verificado_ts = 0.0
            motivo = ("audio_corto_camara_ok" if camara_ok else
                      ("audio_corto_gracia_dueno" if gracia else "audio_corto_sin_camara"))
            self.ultima_verificacion = {
                "es_dueno": es_dueno,
                "similitud": 0.0,
                "camara": camara_ok,
                "gracia_dueno_reciente": gracia,
                "motivo": motivo,
            }
            print(f"[voz_dueno] audio_corto={duracion:.2f}s camara_ok={camara_ok} gracia_dueno_reciente={gracia} permitido={es_dueno}", flush=True)
            return

        # Micro-caché seguro TTL para evitar doble inferencia en el mismo turno
        clave_cache = None
        if audio is not None and isinstance(audio, np.ndarray) and audio.size > 0:
            muestra_hash = hash((audio.size, float(audio[0]), float(audio[-1]), float(audio[audio.size // 2])))
            clave_cache = (audio.size, muestra_hash)
            ahora_m = time.monotonic()
            with _lock_cache:
                hit = _cache_biometria.get(clave_cache)
                if hit and (ahora_m - hit["t"]) < TTL_CACHE_SEG:
                    self.ultima_verificacion = dict(hit["resultado"])
                    if hit.get("embedding") is not None:
                        self.ultimo_embedding = hit["embedding"].copy()
                    return

        try:
            audio_limpio, dur_filtrada = preparar_audio_biometria(audio)
            emb = extraer_embedding(audio_limpio)
            self.ultimo_embedding = emb.copy()
            score, max_sim, n_muestras = calcular_similitud_banco(emb, self.banco_dueno)

            # Tolerancia en clips cortos del dueño (<= 2.5s) con pocos fonemas
            umbral_efectivo = self.umbral
            if dur_filtrada <= 2.5:
                umbral_efectivo = max(0.30, self.umbral - 0.05)

            # Log exacto con score (top-2 promedio para N>=3) y max_sim
            print(f"[voz_dueno] similitud={score:.2f} (max={max_sim:.2f} n={n_muestras}) umbral={self.umbral:.2f} duracion={duracion:.2f}s filtrado={dur_filtrada:.2f}s camara={camara_ok}", flush=True)

            # Doble factor: si la cámara ve al dueño, es válido aunque el puntaje de voz sea bajo
            es_dueno = (score >= umbral_efectivo) or camara_ok
            # Solo la biometría positiva abre la gracia; un rechazo la cancela.
            self._dueno_verificado_ts = time.monotonic() if score >= umbral_efectivo else 0.0
            self.ultima_verificacion = {
                "es_dueno": es_dueno,
                "similitud": score,
                "camara": camara_ok,
                "motivo": "camara" if (camara_ok and score < self.umbral) else ("voz_ok" if es_dueno else "rechazado"),
            }
            if clave_cache is not None:
                with _lock_cache:
                    _cache_biometria[clave_cache] = {
                        "t": time.monotonic(),
                        "resultado": dict(self.ultima_verificacion),
                        "embedding": self.ultimo_embedding.copy(),
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

        if not self.activa or self.banco_dueno is None:
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
        if not os.path.exists(ARCHIVO_VOZ) or self.banco_dueno is None:
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

    def reforzar_voz(self):
        """Refuerza el banco biométrico con la última muestra capturada de la voz del dueño."""
        if self.ultimo_embedding is None:
            self.app.decir("No tengo una muestra reciente de tu voz para reforzar.")
            return
        if self.banco_dueno is None:
            self.app.decir("Aún no has registrado tu voz. Di 'registrar mi voz' primero.")
            return
        nuevo_banco, agregado = agregar_muestra_banco(self.ultimo_embedding, self.banco_dueno)
        if not agregado:
            self.app.decir("Esa muestra de voz ya está registrada en mi banco.")
            return
        self.banco_dueno = nuevo_banco
        self.vector_dueno = nuevo_banco
        guardar_banco(ARCHIVO_VOZ, nuevo_banco)
        n = len(self.banco_dueno)
        print(f"[voz_dueno] Banco reforzado con nueva muestra. Total: {n}", flush=True)
        self.app.decir(f"Voz reforzada con éxito. Ahora tengo {n} muestras de tu voz en el banco.")


def instalar(app):
    """Instala el subsistema de voz del dueño y registra sus acciones."""
    import voz_dueno_registro

    vd = VozDueno(app)
    app.voz_dueno = vd

    acciones.registrar(
        "registrar_mi_voz",
        lambda: voz_dueno_registro.iniciar_registro(app, vd),
        "Guía a Moisés para registrar su voz leyendo 8 frases variadas para reconocimiento biométrico.",
    )
    acciones.registrar(
        "calibrar_voz",
        lambda: voz_dueno_registro.iniciar_calibracion(app, vd),
        "Calibra el umbral de verificación comparando frases de Moisés con frases de otra persona.",
    )
    acciones.registrar(
        "reforzar_mi_voz",
        vd.reforzar_voz,
        "Refuerza el banco biométrico con la última frase hablada por el dueño.",
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
