"""Streaming de voz en tiempo real con Deepgram Aura-2 (PCM linear16 @ 24kHz).

Proporciona baja latencia (~280 ms TTFB) reproduciendo trozos PCM en streaming
mediante sounddevice.RawOutputStream, manteniendo viva la animación labial.
"""
import atexit
import math
import os
import struct
import threading
import time
from typing import Callable, Optional

import config
import httpx

_CLIENTE_LOCK = threading.RLock()
_CLIENTE_HTTP: Optional[httpx.Client] = None
URL_AURA_SPEAK = "https://api.deepgram.com/v1/speak"
MODELO_DEFECTO = "aura-2-celeste-es"
SAMPLE_RATE = 24000
CHANNELS = 1


def _obtener_cliente() -> httpx.Client:
    global _CLIENTE_HTTP
    with _CLIENTE_LOCK:
        if _CLIENTE_HTTP is None or _CLIENTE_HTTP.is_closed:
            _CLIENTE_HTTP = httpx.Client(
                timeout=httpx.Timeout(connect=2.5, read=15.0, write=5.0, pool=10.0),
                limits=httpx.Limits(max_connections=4, max_keepalive_connections=2, keepalive_expiry=18.0),
            )
        return _CLIENTE_HTTP


def _cerrar_cliente():
    global _CLIENTE_HTTP
    with _CLIENTE_LOCK:
        if _CLIENTE_HTTP is not None and not _CLIENTE_HTTP.is_closed:
            try:
                _CLIENTE_HTTP.close()
            except Exception: pass
            _CLIENTE_HTTP = None


atexit.register(_cerrar_cliente)


def aura_disponible() -> bool:
    """Verifica si Deepgram Aura-2 está configurado y habilitado para streaming prioritario."""
    clave = str(getattr(config, "DEEPGRAM_API_KEY", "") or os.environ.get("DEEPGRAM_API_KEY", "")).strip()
    return bool(clave)


def precalentar_conexion():
    """Precalentamiento no bloqueante de TLS en segundo plano usando el singleton."""
    def _tarea():
        try:
            cli = _obtener_cliente()
            cli.get("https://api.deepgram.com", timeout=2.5)
        except Exception: pass
    threading.Thread(target=_tarea, daemon=True, name="aura-warmup").start()


def _calcular_rms_pcm(pcm_bytes: bytes) -> float:
    n_muestras = len(pcm_bytes) // 2
    if n_muestras == 0: return 0.0
    try:
        muestras = struct.unpack(f"<{n_muestras}h", pcm_bytes[:n_muestras * 2])
        rms = math.sqrt(sum(s * s for s in muestras) / n_muestras)
        rms_norm = rms / 32768.0
        if rms_norm <= 0.001: return 0.0
        return min(1.0, (rms_norm ** 0.65) * 2.4)
    except Exception: return 0.0


def reproducir_stream_aura(
    texto: str,
    cancelar_fn: Optional[Callable[[], bool]] = None,
    al_iniciar: Optional[Callable[[], None]] = None,
    al_nivel: Optional[Callable[[float], None]] = None,
    timeout: float = 3.5,
) -> bool:
    txt = (texto or "").strip()
    if not txt: return False

    clave = str(getattr(config, "DEEPGRAM_API_KEY", "") or os.environ.get("DEEPGRAM_API_KEY", "")).strip()
    if not clave: return False
    if cancelar_fn and cancelar_fn(): return True

    modelo = str(os.environ.get("LYRIS_AURA_MODELO") or getattr(config, "MODELO_AURA", "") or MODELO_DEFECTO).strip()
    url = f"{URL_AURA_SPEAK}?model={modelo}&encoding=linear16&sample_rate={SAMPLE_RATE}&container=none"
    headers = {"Authorization": f"Token {clave}", "Content-Type": "application/json"}

    try:
        import sounddevice as sd
    except Exception as e:
        print(f"[voz] sounddevice no disponible ({e}), usando fallback", flush=True)
        return False

    CHUNK_BYTES = 1920  # ~40 ms de audio linear16 a 24 kHz (25 updates/seg)

    def _ejecutar_transmision() -> tuple[bool, bool]:
        t0 = time.time()
        cli = _obtener_cliente()
        empezo = False
        sobrante = b""
        req = cli.build_request("POST", url, headers=headers, json={"text": txt}, timeout=timeout)
        resp = cli.send(req, stream=True)
        if resp.status_code != 200:
            print(f"[voz] deepgram tts HTTP {resp.status_code}, usando fallback", flush=True)
            resp.close()
            return False, False

        try:
            with sd.RawOutputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16", blocksize=960) as stream:
                for trozo in resp.iter_bytes(chunk_size=CHUNK_BYTES):
                    if cancelar_fn and cancelar_fn():
                        resp.close()
                        return True, empezo
                    if not trozo: continue
                    datos = sobrante + trozo
                    if len(datos) % 2 != 0:
                        sobrante, datos = datos[-1:], datos[:-1]
                    else:
                        sobrante = b""
                    if not datos: continue

                    if not empezo:
                        empezo = True
                        ttfb = int((time.time() - t0) * 1000)
                        print(f"[voz] motor=deepgram_aura_stream modelo={modelo} ttfb={ttfb}ms", flush=True)
                        if al_iniciar:
                            try: al_iniciar()
                            except Exception: pass

                    if al_nivel:
                        try: al_nivel(_calcular_rms_pcm(datos))
                        except Exception: pass

                    stream.write(datos)
        finally:
            resp.close()
        return empezo, empezo

    try:
        for intento in range(2):
            try:
                ok, empezo_audio = _ejecutar_transmision()
                if ok or empezo_audio:
                    return True
                return False
            except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as err_red:
                if intento == 0:
                    print(f"[voz] socket aura cerrado ({err_red}), reiniciando cliente y reintentando...", flush=True)
                    _cerrar_cliente()
                    continue
                print(f"[voz] reintento aura falló ({err_red}), usando fallback", flush=True)
                return False
            except Exception as e:
                print(f"[voz] fallo en aura stream ({e}), usando fallback", flush=True)
                return False
        return False
    finally:
        if al_nivel:
            try: al_nivel(0.0)
            except Exception: pass


def procesar_frase_productor(voz_obj, frase, emo):
    """Decide si sintetiza audio o si pasa directo a streaming sin bloquear el hilo."""
    import voz_cache, voz_local
    en_cache = voz_cache.obtener_audio_cache(frase, emo)
    if en_cache or voz_local.debe_ir_local_primero() or not aura_disponible():
        return voz_obj._audio(frase, emo)
    return None


def procesar_frase_consumidor(voz_obj, frase, audio, emo, gen, ver, al_ini, al_niv):
    """Intenta streaming Aura-2; si falla o no aplica, retorna el audio listo para reproductor."""
    import voz_local
    if not audio and not voz_local.debe_ir_local_primero():
        try:
            if reproducir_stream_aura(frase, lambda: ver != voz_obj.version, al_ini, al_niv):
                if ver != voz_obj.version:
                    print(f"[voz] cancelada motivo=interrupcion frase='{frase}'", flush=True)
                else:
                    voz_obj.sincronia_labial.finalizar(gen)
                    print(f"[voz] terminó='{frase}'", flush=True)
                return True, None
        except Exception as e:
            print(f"[voz] aura stream error ({e}), usando fallback...", flush=True)
    if not audio:
        try:
            audio = voz_obj._audio(frase, emo)
        except Exception:
            audio = None
    return False, audio
