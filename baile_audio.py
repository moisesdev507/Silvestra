"""Motor de audio rítmico local sin anuncios para las coreografías de Silvestra."""
import os
import time
import wave
import numpy as np

DURACION_BAILE_SEG = 15.0
CARPETA_SONIDOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sonidos")
CARPETA_USUARIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "musica_baile")

_AUDIO_ACTIVO = False
_TIEMPO_INICIO = 0.0
_CANAL_ACTIVO = None
_SONIDO_CACHE = {}


def _inicializar_mixer_seguro():
    try:
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
    except Exception:
        pass


_inicializar_mixer_seguro()


def _normalizar_y_guardar(ruta, audio, rate=22050, fade_in=0.4, fade_out=1.2, vol=0.38):
    """Aplica fade-in/fade-out, volumen moderado y guarda en WAV PCM 16-bit."""
    n_in = int(rate * fade_in)
    n_out = int(rate * fade_out)
    arr = audio.astype(np.float32)
    if n_in > 0 and len(arr) >= n_in:
        arr[:n_in] *= np.linspace(0.0, 1.0, n_in, dtype=np.float32)
    if n_out > 0 and len(arr) >= n_out:
        arr[-n_out:] *= np.linspace(1.0, 0.0, n_out, dtype=np.float32)
    pico = float(np.max(np.abs(arr)))
    if pico > 0.001:
        arr = (arr / pico) * float(vol)
    pcm = np.clip(arr * 32767.0, -32768.0, 32767.0).astype(np.int16)
    with wave.open(ruta, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm.tobytes())


def _sintetizar_groove(dur=15.0, rate=22050):
    """Beat funk/groove rítmico a ~108 BPM."""
    n = int(rate * dur)
    t = np.linspace(0, dur, n, endpoint=False, dtype=np.float32)
    out = np.zeros(n, dtype=np.float32)
    bpm = 108.0
    spb = 60.0 / bpm
    total_beats = int(dur / spb)

    for b in range(total_beats):
        tb = b * spb
        idx_b = int(tb * rate)
        # 1. Bombo en tiempo 1 y síncopa en 2.75
        for offset_beat in (0.0, 1.75):
            k_t0 = tb + offset_beat * spb
            k_idx = int(k_t0 * rate)
            k_len = int(0.28 * rate)
            if k_idx + k_len <= n:
                kt = np.linspace(0, 0.28, k_len, endpoint=False, dtype=np.float32)
                frec = 130.0 * np.exp(-14.0 * kt) + 45.0
                out[k_idx : k_idx + k_len] += 0.85 * np.sin(2 * np.pi * frec * kt) * np.exp(-10.0 * kt)

        # 2. Caja/clap en tiempo 2 y 4
        for offset_beat in (1.0, 3.0):
            if b % 4 == int(offset_beat):
                s_idx = idx_b
                s_len = int(0.20 * rate)
                if s_idx + s_len <= n:
                    st = np.linspace(0, 0.20, s_len, endpoint=False, dtype=np.float32)
                    ruido = np.random.uniform(-0.5, 0.5, s_len).astype(np.float32) * np.exp(-18.0 * st)
                    cuerpo = 0.4 * np.sin(2 * np.pi * 190.0 * st) * np.exp(-22.0 * st)
                    out[s_idx : s_idx + s_len] += ruido + cuerpo

        # 3. Hi-hats en semicorcheas
        for sub in range(4):
            h_idx = int((tb + sub * (spb / 4.0)) * rate)
            h_len = int(0.045 * rate)
            if h_idx + h_len <= n:
                ht = np.linspace(0, 0.045, h_len, endpoint=False, dtype=np.float32)
                vol_h = 0.35 if sub % 2 == 1 else 0.22
                out[h_idx : h_idx + h_len] += np.random.uniform(-vol_h, vol_h, h_len).astype(np.float32) * np.exp(-55.0 * ht)

        # 4. Línea de bajo funk pentatónico
        notas_bajo = [73.4, 73.4, 87.3, 98.0, 116.5, 98.0, 87.3, 73.4]
        f_b = notas_bajo[b % len(notas_bajo)]
        b_len = int(0.42 * rate)
        if idx_b + b_len <= n:
            bt = np.linspace(0, 0.42, b_len, endpoint=False, dtype=np.float32)
            onda_b = np.sin(2 * np.pi * f_b * bt) + 0.45 * np.sin(2 * np.pi * f_b * 2.0 * bt)
            out[idx_b : idx_b + b_len] += 0.70 * onda_b * np.exp(-6.5 * bt)

    return out


def _sintetizar_salsa(dur=15.0, rate=22050):
    """Clave y tumbao latino alegre a ~118 BPM."""
    n = int(rate * dur)
    out = np.zeros(n, dtype=np.float32)
    bpm = 118.0
    spb = 60.0 / bpm
    total_beats = int(dur / spb)

    for b in range(total_beats):
        tb = b * spb
        # 1. Clave 2-3
        paso_compas = b % 4
        golpes_clave = [0.0, 1.5, 3.0] if (b // 4) % 2 == 0 else [1.0, 2.5]
        for g in golpes_clave:
            if paso_compas == int(g):
                c_idx = int((tb + (g - int(g)) * spb) * rate)
                c_len = int(0.065 * rate)
                if c_idx + c_len <= n:
                    ct = np.linspace(0, 0.065, c_len, endpoint=False, dtype=np.float32)
                    clave = (np.sin(2 * np.pi * 2250.0 * ct) + 0.3 * np.sin(2 * np.pi * 1480.0 * ct)) * np.exp(-50.0 * ct)
                    out[c_idx : c_idx + c_len] += 0.75 * clave

        # 2. Conga / Campana ligera
        c_idx = int(tb * rate)
        c_len = int(0.18 * rate)
        if c_idx + c_len <= n:
            ct = np.linspace(0, 0.18, c_len, endpoint=False, dtype=np.float32)
            f_conga = 280.0 if (b % 2 == 0) else 190.0
            out[c_idx : c_idx + c_len] += 0.45 * np.sin(2 * np.pi * f_conga * ct) * np.exp(-15.0 * ct)

        # 3. Montuno de piano / acordes rítmicos (C / G)
        acorde = [261.6, 329.6, 392.0] if (b % 8 < 4) else [246.9, 293.7, 392.0]
        m_len = int(0.22 * rate)
        if c_idx + m_len <= n:
            mt = np.linspace(0, 0.22, m_len, endpoint=False, dtype=np.float32)
            sonido_acorde = np.zeros(m_len, dtype=np.float32)
            for f in acorde:
                sonido_acorde += np.sin(2 * np.pi * f * mt) * 0.22
            out[c_idx : c_idx + m_len] += sonido_acorde * np.exp(-9.0 * mt)

    return out


def _sintetizar_fiesta(dur=15.0, rate=22050):
    """Synth-pop bailable y energético a ~126 BPM."""
    n = int(rate * dur)
    out = np.zeros(n, dtype=np.float32)
    bpm = 126.0
    spb = 60.0 / bpm
    total_beats = int(dur / spb)

    for b in range(total_beats):
        tb = b * spb
        idx_b = int(tb * rate)
        # 1. Four-on-the-floor kick contundente
        k_len = int(0.24 * rate)
        if idx_b + k_len <= n:
            kt = np.linspace(0, 0.24, k_len, endpoint=False, dtype=np.float32)
            frec = 150.0 * np.exp(-16.0 * kt) + 48.0
            out[idx_b : idx_b + k_len] += 0.95 * np.sin(2 * np.pi * frec * kt) * np.exp(-11.0 * kt)

        # 2. Open Hi-Hat en el contratiempo (upbeat)
        oh_idx = int((tb + 0.5 * spb) * rate)
        oh_len = int(0.12 * rate)
        if oh_idx + oh_len <= n:
            oht = np.linspace(0, 0.12, oh_len, endpoint=False, dtype=np.float32)
            out[oh_idx : oh_idx + oh_len] += np.random.uniform(-0.38, 0.38, oh_len).astype(np.float32) * np.exp(-22.0 * oht)

        # 3. Arpegio synth electro brillante
        arpegio = [220.0, 261.6, 329.6, 440.0, 329.6, 261.6, 220.0, 164.8]
        for sub in range(2):
            s_idx = int((tb + sub * (spb / 2.0)) * rate)
            s_len = int(0.20 * rate)
            if s_idx + s_len <= n:
                st = np.linspace(0, 0.20, s_len, endpoint=False, dtype=np.float32)
                f_s = arpegio[(b * 2 + sub) % len(arpegio)]
                onda = np.sin(2 * np.pi * f_s * st) + 0.4 * np.sin(2 * np.pi * f_s * 2.0 * st) + 0.2 * np.sin(2 * np.pi * f_s * 3.0 * st)
                out[s_idx : s_idx + s_len] += 0.55 * onda * np.exp(-9.0 * st)

    return out


def generar_bases_locales(forzar=False):
    """Crea los 3 archivos WAV rítmicos en sonidos/ si no existen."""
    os.makedirs(CARPETA_SONIDOS, exist_ok=True)
    generadores = {
        "groove": _sintetizar_groove,
        "salsa": _sintetizar_salsa,
        "fiesta": _sintetizar_fiesta,
    }
    for estilo, fn in generadores.items():
        ruta = os.path.join(CARPETA_SONIDOS, f"baile_{estilo}.wav")
        if forzar or not os.path.exists(ruta):
            try:
                audio = fn(DURACION_BAILE_SEG)
                _normalizar_y_guardar(ruta, audio)
                print(f"[baile_audio] Base sintetizada local: {estilo}", flush=True)
            except Exception as e:
                print(f"[baile_audio] Error sintetizando {estilo}: {e}", flush=True)


def _buscar_musica_local(estilo):
    """Busca en musica_baile/ personalizada o retorna el WAV cacheado en sonidos/."""
    est = str(estilo or "groove").lower().strip()
    if os.path.exists(CARPETA_USUARIO):
        for arch in os.listdir(CARPETA_USUARIO):
            base, ext = os.path.splitext(arch.lower())
            if ext in (".wav", ".mp3") and (est in base or "baile" in base):
                return os.path.join(CARPETA_USUARIO, arch)

    ruta_base = os.path.join(CARPETA_SONIDOS, f"baile_{est}.wav")
    if not os.path.exists(ruta_base):
        generar_bases_locales(forzar=False)
    if os.path.exists(ruta_base):
        return ruta_base
    return None


def reproducir_musica_baile(estilo="groove"):
    """Inicia la pista rítmica local de 15 segundos sin bloquear el hilo principal."""
    global _AUDIO_ACTIVO, _TIEMPO_INICIO, _CANAL_ACTIVO
    detener_musica_baile()

    ruta = _buscar_musica_local(estilo)
    if not ruta or not os.path.exists(ruta):
        return False

    _AUDIO_ACTIVO = True
    _TIEMPO_INICIO = time.time()
    print(f"[baile_audio] Reproduciendo musica local ({estilo}) sin anuncios", flush=True)

    # 1. Intentar con pygame.mixer (motor SDL ultra-rápido ~0.01ms, sin bloquear Qt)
    try:
        import pygame
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init()
            except Exception:
                pass
        if pygame.mixer.get_init():
            snd = _SONIDO_CACHE.get(ruta)
            if snd is None:
                snd = pygame.mixer.Sound(ruta)
                _SONIDO_CACHE[ruta] = snd
            # Usar canal dedicado 6 para no colisionar con la voz
            canal = pygame.mixer.Channel(6)
            canal.set_volume(0.40)
            canal.play(snd)
            _CANAL_ACTIVO = canal
            return True
    except Exception as e:
        print(f"[baile_audio] Fallo pygame.mixer: {e}", flush=True)

    # 2. Fallback con winsound en hilo daemon
    try:
        import winsound

        def _iniciar_reproduccion():
            try:
                winsound.PlaySound(ruta, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception:
                pass

        import threading
        threading.Thread(target=_iniciar_reproduccion, daemon=True).start()
        return True
    except Exception as e2:
        print(f"[baile_audio] Fallo winsound: {e2}", flush=True)
        return False


def detener_musica_baile():
    """Detiene cualquier audio rítmico local de inmediato."""
    global _AUDIO_ACTIVO, _CANAL_ACTIVO
    if not _AUDIO_ACTIVO and _CANAL_ACTIVO is None:
        return
    _AUDIO_ACTIVO = False
    if _CANAL_ACTIVO is not None:
        try:
            _CANAL_ACTIVO.stop()
        except Exception:
            pass
        _CANAL_ACTIVO = None
    try:
        import winsound
        winsound.PlaySound(None, 0)
    except Exception:
        pass
