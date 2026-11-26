"""Oído clásico en streaming continuo hacia Deepgram Nova-3 por WebSocket.

Envía bloques PCM a medida que el VAD los produce (sin subir un WAV completo),
usa ``additional_headers`` para autenticar con ``websockets 17.4`` y cae a
``oido_deepgram`` (HTTP) ante cualquier corte, error o timeout.
"""
import json
import os
import time

import config

URL = "wss://api.deepgram.com/v1/listen"
MODELO = "nova-3"
IDIOMA = "es-419"
ENDPOINTING_MS = 900
TIMEOUT_APERTURA = 3.0
TIMEOUT_CIERRE = 2.0
MENSAJE_FINALIZE = '{"type": "Finalize"}'

try:
    from identidad_kaya import KEYTERM_DEEPGRAM as KEYTERM
except Exception:
    KEYTERM = "Kaya:10,Kaia:6,Caya:5"


def _clave():
    return str(
        getattr(config, "DEEPGRAM_API_KEY", "")
        or os.environ.get("DEEPGRAM_API_KEY", "")
    ).strip()


def url_stream():
    return (
        f"{URL}?model={MODELO}&language={IDIOMA}&smart_format=true"
        f"&interim_results=true&endpointing={ENDPOINTING_MS}"
        "&encoding=linear16&sample_rate=16000&channels=1"
        f"&keyterm={KEYTERM}"
    )


def _conectar(url, clave):
    """Apertura sincrónica; ``additional_headers`` es la API de websockets 17.4."""
    from websockets.sync.client import connect

    return connect(
        url,
        additional_headers={"Authorization": f"Token {clave}"},
        open_timeout=TIMEOUT_APERTURA,
        close_timeout=0.3,
        ping_interval=None,
    )


def _es_cierre_limpio(exc):
    """Deepgram cierra con 1000 al terminar el endpointing: no es un fallo."""
    texto = str(exc)
    return "1000" in texto or "ConnectionClosedOK" in type(exc).__name__


def _es_finalize(mensaje):
    """True si Deepgram cerró la transcripción tras recibir {"type": "Finalize"}."""
    return isinstance(mensaje, str) and '"FinalResults"' in mensaje.replace(" ", "")


def _texto_mensaje(mensaje):
    """Extrae la transcripción final de un mensaje de resultados de Deepgram."""
    try:
        datos = json.loads(mensaje)
    except Exception:
        return ""
    if datos.get("type") == "FinalResults":
        canales = (datos.get("result") or {}).get("channels", [])
    else:
        if not datos.get("is_final"):
            return ""
        canales = (datos.get("result") or {}).get("channels", [])
    for canal in canales:
        alternativas = canal.get("alternatives") or []
        if alternativas:
            return " ".join(str(alternativas[0].get("transcript") or "").split())
    return ""


def _confianza_mensaje(mensaje):
    """Lee channel.alternatives[0].confidence del resultado final de Deepgram."""
    try:
        datos = json.loads(mensaje)
    except Exception:
        return None
    if not (datos.get("type") == "FinalResults" or datos.get("is_final")):
        return None
    for canal in (datos.get("result") or {}).get("channels", []):
        alternativas = canal.get("alternatives") or []
        if alternativas:
            try:
                return float(alternativas[0].get("confidence"))
            except (TypeError, ValueError):
                return None
    return None


class SesionStreaming:
    """Sesión WS incremental con respaldo HTTP transparente."""

    def __init__(self, clave=None):
        self.clave = clave if clave is not None else _clave()
        self.ws = None
        self.activa = False
        self.chunks = []
        self.texto_final = ""
        self.confianza = 1.0
        self.inicio = time.monotonic()
        self.fallo = None

    def iniciar(self):
        if not self.clave:
            self.fallo = "sin clave Deepgram"
            return False
        try:
            self.ws = _conectar(url_stream(), self.clave)
            self.activa = True
            print("[oido] WS Deepgram abierto (streaming continuo).", flush=True)
            return True
        except Exception as exc:
            self.fallo = exc
            print(f"[oido] WS no disponible ({str(exc)[:80]}): fallback HTTP listo.", flush=True)
            return False

    def enviar(self, chunk, conservar=True):
        """Envía el bloque al WS; ``conservar=False`` evita duplicar silencio en el fallback."""
        if not chunk:
            return
        if conservar:
            self.chunks.append(bytes(chunk))
        if not self.activa:
            return
        try:
            self.ws.send(bytes(chunk))
        except Exception as exc:
            self.activa = False
            self.fallo = exc
            if _es_cierre_limpio(exc):
                print("[oido] WS cerrado por Deepgram (1000): usando resultados recibidos.", flush=True)
            else:
                print(f"[oido] WS cortado ({str(exc)[:80]}): usando HTTP al cerrar.", flush=True)

    def _acumular_texto(self, texto):
        """Ensambla los resultados finales sin repetir el texto ya recibido."""
        texto = " ".join(str(texto or "").split())
        if not texto:
            return
        if not self.texto_final:
            self.texto_final = texto
        elif texto in self.texto_final:
            return
        elif self.texto_final in texto:
            self.texto_final = texto
        else:
            self.texto_final = f"{self.texto_final} {texto}"

    def _leer_resultados(self):
        fin = time.monotonic() + TIMEOUT_CIERRE
        while time.monotonic() < fin:
            restante = max(0.05, fin - time.monotonic())
            try:
                mensaje = self.ws.recv(timeout=restante)
            except Exception:
                break
            if mensaje is None:
                break
            texto = _texto_mensaje(mensaje)
            if texto:
                self._acumular_texto(texto)
                confianza = _confianza_mensaje(mensaje)
                if confianza is not None:
                    self.confianza = confianza
            if _es_finalize(mensaje):
                break

    def cerrar(self):
        """Cierra el socket con código limpio 1000, aun si hubo corte."""
        if self.ws is not None:
            try:
                self.ws.close(code=1000)
            except Exception:
                pass
            self.ws = None
        self.activa = False

    def finalizar(self):
        """Pide el resultado final con Finalize, espera is_final y cierra con 1000."""
        try:
            if self.activa and self.ws is not None:
                try:
                    self.ws.send(MENSAJE_FINALIZE)
                except Exception as exc:
                    self.activa = False
                    self.fallo = exc
                    if not _es_cierre_limpio(exc):
                        print(f"[oido] Finalize no enviado ({str(exc)[:60]}).", flush=True)
                self._leer_resultados()
        finally:
            self.cerrar()

        duracion = sum(len(c) for c in self.chunks) / (16000.0 * 2.0)
        if self.texto_final:
            ms = round((time.monotonic() - self.inicio) * 1000.0)
            print(f"[tiempo] clasico_stt={ms}ms (ws)", flush=True)
            return self.texto_final, duracion, self.confianza

        print(f"[oido] WS sin transcripción: fallback HTTP "
              f"({len(self.chunks)} bloques de voz, {duracion:.2f}s).", flush=True)
        return self._fallback_http()

    def _fallback_http(self):
        import io

        import numpy as np
        import oido_deepgram
        import oido_flujo

        crudo = b"".join(self.chunks)
        if not crudo:
            return None
        audio = np.frombuffer(crudo, dtype=np.int16)
        wav = oido_flujo.crear_buffer_wav(audio, rate=16000).getvalue()
        t0 = time.monotonic()
        try:
            resultado = oido_deepgram.transcribir(wav)
        except Exception as exc:
            print(f"[oido] Fallback HTTP falló: {exc}", flush=True)
            return None
        ms = round((time.monotonic() - t0) * 1000.0)
        print(f"[tiempo] clasico_stt={ms}ms (http)", flush=True)
        if not resultado:
            return None
        if len(resultado) >= 3:
            return resultado
        return resultado[0], resultado[1], 1.0


def transcribir(chunks, clave=None):
    """Atajo: stream de chunks ya capturados; devuelve (texto, duracion, confianza)."""
    sesion = SesionStreaming(clave=clave)
    sesion.iniciar()
    for chunk in chunks or ():
        sesion.enviar(chunk)
    return sesion.finalizar()
