"""Síntesis de voz con Salomé (edge-tts) por defecto y respaldo rápido local/Aura.

Prioridad:
1. Caché persistente.
2. Motor principal: edge-tts (es-CO-SalomeNeural).
3. Respaldo rápido: Kokoro/Piper local (~80 ms) o Deepgram Aura-2 (~200 ms).
4. Respaldo final: Piper local / SAPI Windows.
"""
import os
import re
import threading

import config
import httpx
import voz_cache
import voz_local

_LOCK = threading.RLock()
URL_DEEPGRAM_TTS = "https://api.deepgram.com/v1/speak"
MODELO_AURA = "aura-2-celeste-es"


def sintetizar_deepgram(frase):
    """Genera audio con Deepgram Aura-2 TTS; None si falla o no hay clave."""
    clave = str(getattr(config, "DEEPGRAM_API_KEY", "")
                or os.environ.get("DEEPGRAM_API_KEY", "")).strip()
    if not clave or not frase or not frase.strip():
        return None
    url = f"{URL_DEEPGRAM_TTS}?model={MODELO_AURA}"
    headers = {
        "Authorization": f"Token {clave}",
        "Content-Type": "application/json",
    }
    payload = {"text": frase.strip()}
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=3.5)
        if resp.status_code == 200 and resp.content:
            print(f"[voz] motor=deepgram_aura modelo={MODELO_AURA}", flush=True)
            return resp.content
        print(f"[voz] deepgram tts HTTP {resp.status_code}, usando fallback", flush=True)
    except Exception:
        pass
    return None


def sintetizar_rapido(frase, emocion="neutral"):
    """Intenta síntesis ultra-rápida (Kokoro/Piper local o Deepgram Aura)."""
    # 1. Kokoro / Piper VITS local (~80 ms offline)
    if voz_local.disponible():
        audio = voz_local.sintetizar_wav(frase, emocion)
        if audio:
            print("[voz] motor=piper_local", flush=True)
            return audio

    # 2. Deepgram Aura-2 TTS (~200 ms)
    audio_dg = sintetizar_deepgram(frase)
    if audio_dg:
        return audio_dg

    return None


def sintetizar_edge(frase, emocion="neutral"):
    """Síntesis de alta calidad con edge-tts (Salomé)."""
    import edge_tts
    import voz_estilo
    from voz import EMOCIONES_VOZ, normalizar_emocion

    emo = normalizar_emocion(emocion)
    a = voz_estilo.ajustes(emo, EMOCIONES_VOZ.get(emo))
    rate, pitch, volume = a["rate"], a["pitch"], a["volume"]
    voz = voz_estilo.voz_actual()
    print(f"[voz] motor=edge_tts voz={voz} emocion={emo} rate={rate} pitch={pitch}", flush=True)

    async def crear():
        datos = bytearray()
        async for trozo in edge_tts.Communicate(frase, voz, rate=rate, pitch=pitch, volume=volume).stream():
            if trozo["type"] == "audio":
                datos += trozo["data"]
        return bytes(datos)

    return voz_local.generar_edge(crear, frase, emocion)


def sintetizar_cadena(frase, emocion="neutral"):
    """Cadena: Cache -> Aura-2 (Celeste) -> Edge-TTS (Salomé respaldo) -> Respaldo local."""
    en_cache = voz_cache.obtener_audio_cache(frase, emocion)
    if en_cache:
        return en_cache

    if voz_local.debe_ir_local_primero():
        audio_local = voz_local.fallback_local(frase, emocion)
        if audio_local:
            return audio_local

    # Motor principal: Deepgram Aura-2 (Celeste)
    audio_dg = sintetizar_deepgram(frase)
    if audio_dg:
        return audio_dg

    # Respaldo 1: edge-tts (Salomé) ante falta de clave o fallo de red
    audio_edge = sintetizar_edge(frase, emocion)
    if audio_edge:
        return audio_edge

    # Respaldo 2: motor local final
    return voz_local.fallback_local(frase, emocion) or b""
