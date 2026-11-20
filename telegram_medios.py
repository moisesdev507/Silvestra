"""Gestor de medios, notas de voz, fotos y capturas para Telegram en Silvestra."""
from __future__ import annotations

import base64
import io
import re
import threading
import time
from typing import Any, Optional
from PIL import Image, ImageGrab
import requests

from telegram_medios_proc import (
    sanitizar_privacidad,
    transcribir_audio,
    analizar_imagen_vision,
    verificar_privacidad_pantalla,
)

MAX_BYTES_ARCHIVO = 10 * 1024 * 1024  # 10 MB
MAX_IMAGENES_HORA = 20


def descargar_archivo_telegram(token: str, file_id: str, max_tam: int = MAX_BYTES_ARCHIVO) -> tuple[Optional[bytes], Optional[str]]:
    """Descarga un archivo de Telegram directamente a memoria."""
    url_info = f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
    try:
        r = requests.get(url_info, timeout=15)
        if r.status_code != 200:
            return None, f"status={r.status_code}"
        datos = r.json()
        if not datos.get("ok"):
            return None, "respuesta_invalida"
        res = datos.get("result", {})
        if res.get("file_size", 0) > max_tam:
            return None, "archivo_muy_grande"
        file_path = res.get("file_path")
        if not file_path:
            return None, "sin_ruta"
        r_down = requests.get(f"https://api.telegram.org/file/bot{token}/{file_path}", timeout=30)
        return (r_down.content, None) if r_down.status_code == 200 else (None, f"down_status={r_down.status_code}")
    except Exception as e:
        return None, str(e)


class GestorMediosTelegram:
    """Administra recepción de notas de voz, fotos y envío de capturas/cámara."""

    def __init__(self, puente: Any):
        self.puente = puente
        self.app = puente.app
        self.historial_imagenes_enviadas: list[float] = []
        self._bloqueo_limite = threading.Lock()

    def _puede_enviar_imagen(self) -> bool:
        """Aplica la cuota de máximo 20 imágenes enviadas por hora."""
        with self._bloqueo_limite:
            ahora = time.time()
            self.historial_imagenes_enviadas = [t for t in self.historial_imagenes_enviadas if ahora - t < 3600]
            if len(self.historial_imagenes_enviadas) >= MAX_IMAGENES_HORA:
                return False
            self.historial_imagenes_enviadas.append(ahora)
            return True

    def enviar_foto(self, chat_id: int, foto_bytes: bytes, caption: Optional[str] = None, tipo: str = "imagen") -> bool:
        """Envía una foto en memoria por Telegram y registra en log sin tocar disco."""
        if not self._puede_enviar_imagen():
            print(f"[telegram] Envío bloqueado: límite de {MAX_IMAGENES_HORA} imágenes/hora alcanzado.", flush=True)
            self.puente._enviar_telegram(
                chat_id,
                f"Alcancé el límite de seguridad de {MAX_IMAGENES_HORA} imágenes por hora. Por favor espera un momento.",
            )
            return False

        url = f"https://api.telegram.org/bot{self.puente.token}/sendPhoto"
        files = {"photo": ("imagen.jpg", foto_bytes, "image/jpeg")}
        data: dict[str, Any] = {"chat_id": chat_id}
        if caption:
            data["caption"] = sanitizar_privacidad(caption)

        try:
            r = requests.post(url, files=files, data=data, timeout=30)
            if r.status_code == 200:
                print(f"[telegram] Imagen enviada tipo={tipo} chat_id={chat_id} ({len(foto_bytes)} bytes)", flush=True)
                return True
            print(f"[telegram] Error enviando imagen tipo={tipo}: status={r.status_code}", flush=True)
        except Exception as e:
            print(f"[telegram] Excepción enviando imagen tipo={tipo}: {e}", flush=True)
        return False

    def procesar_nota_voz(self, msg: dict[str, Any]) -> None:
        """Procesa nota de voz entrante con Whisper y responde con Edge-TTS + texto."""
        chat_id = msg.get("chat", {}).get("id")
        audio_info = msg.get("voice") or msg.get("audio")
        if not audio_info or not audio_info.get("file_id"):
            return

        bytes_audio, err = descargar_archivo_telegram(self.puente.token, audio_info["file_id"])
        if err == "archivo_muy_grande":
            self.puente._enviar_telegram(chat_id, "El audio supera el límite permitido de 10 MB.")
            return
        if not bytes_audio:
            print(f"[telegram] Error descargando audio: {err}", flush=True)
            self.puente._enviar_telegram(chat_id, "No pude descargar tu nota de voz.")
            return

        nombre = "nota.ogg" if "voice" in msg else "nota.mp3"
        texto = transcribir_audio(self.app, bytes_audio, nombre=nombre)
        if not texto or len(texto) < 2:
            self.puente._enviar_telegram(chat_id, "No logré entender tu nota de voz, ¿me la podrías repetir?")
            return

        print(f"[telegram] Nota de voz transcrita: '{texto}' (longitud={len(texto)})", flush=True)
        if hasattr(self.app, "cuidado") and self.app.cuidado:
            try:
                self.app.cuidado.notificar_senal_usuario("telegram_voz", texto)
            except Exception:
                pass

        try:
            resp, *resto = self.app.cerebro.responder(texto)
            emocion_resp = resto[1] if len(resto) > 1 else (resto[0] if resto else "calida")
        except Exception as e:
            print(f"[telegram] Error en cerebro para nota de voz: {e}", flush=True)
            self.puente._enviar_telegram(chat_id, "Tuve un problema para procesar tu nota de voz.")
            return

        resp_sani = sanitizar_privacidad(resp)
        import cuidado
        audio_resp = cuidado.sintetizar_audio_mp3(resp_sani, emocion=emocion_resp)
        if audio_resp:
            self.puente.enviar_audio(audio_resp, caption=resp_sani)
        else:
            self.puente._enviar_telegram(chat_id, resp_sani)

        self.app.cola.put(("telegram_burbuja", f"[Nota de voz]: {texto}\n{resp_sani}"))

    def procesar_foto(self, msg: dict[str, Any]) -> None:
        """Procesa una foto entrante con el modelo de visión multimodal."""
        chat_id = msg.get("chat", {}).get("id")
        fotos = msg.get("photo", [])
        if not fotos or not fotos[-1].get("file_id"):
            return

        bytes_foto, err = descargar_archivo_telegram(self.puente.token, fotos[-1]["file_id"])
        if err == "archivo_muy_grande":
            self.puente._enviar_telegram(chat_id, "La foto supera el límite permitido de 10 MB.")
            return
        if not bytes_foto:
            print(f"[telegram] Error descargando foto: {err}", flush=True)
            self.puente._enviar_telegram(chat_id, "No pude descargar la foto enviada.")
            return

        caption = msg.get("caption", "")
        pedir_voz = bool(
            re.search(
                r"\b(nota de voz|en voz alta|con audio|dilo|dímelo|dímelo en voz alta|léelo|léelo en voz alta)\b",
                caption,
                re.I,
            )
        )
        resp = analizar_imagen_vision(self.app, bytes_foto, pregunta=caption)
        resp_sani = sanitizar_privacidad(resp)

        if pedir_voz:
            import cuidado
            audio_resp = cuidado.sintetizar_audio_mp3(resp_sani)
            if audio_resp:
                self.puente.enviar_audio(audio_resp, caption=resp_sani)
            else:
                self.puente._enviar_telegram(chat_id, resp_sani)
        else:
            self.puente._enviar_telegram(chat_id, resp_sani)

        self.app.cola.put(("telegram_burbuja", f"[Foto]: {resp_sani}"))

    def enviar_captura_pantalla(self, chat_id: int, avisar_en_voz: bool = False) -> None:
        """Captura la pantalla en memoria, verifica privacidad y la envía a Telegram."""
        if not self._puede_enviar_imagen():
            self.puente._enviar_telegram(chat_id, f"Alcancé el límite de {MAX_IMAGENES_HORA} imágenes por hora.")
            return

        try:
            img = ImageGrab.grab()
            if img.width > 1280:
                img = img.resize((1280, int(img.height * (1280 / img.width))), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=75)
            foto_bytes = buf.getvalue()
            b64 = base64.b64encode(foto_bytes).decode("utf-8")
        except Exception as e:
            print(f"[telegram] Error capturando pantalla: {e}", flush=True)
            self.puente._enviar_telegram(chat_id, "No pude tomar la captura de pantalla.")
            return

        es_segura, motivo = verificar_privacidad_pantalla(self.app, b64)
        if not es_segura:
            self.puente._enviar_telegram(
                chat_id,
                "Moisés, detecté que la pantalla contiene claves o contraseñas, así que por seguridad no te envié la captura.",
            )
            if avisar_en_voz:
                self.app.cola.put(("hablar", "Detecté contraseñas en tu pantalla, así que por seguridad no envié la captura."))
            return

        ok = self.enviar_foto(chat_id, foto_bytes, caption="Aquí tienes la captura de mi pantalla.", tipo="captura")
        if ok and avisar_en_voz:
            self.app.cola.put(("hablar", "Te acabo de enviar la captura de mi pantalla a tu Telegram."))

    def enviar_foto_camara(self, chat_id: int, avisar_en_voz: bool = False) -> None:
        """Captura un fotograma de la cámara en memoria y lo envía a Telegram."""
        if not self._puede_enviar_imagen():
            self.puente._enviar_telegram(chat_id, f"Alcancé el límite de {MAX_IMAGENES_HORA} imágenes por hora.")
            return

        if not hasattr(self.app, "camara") or self.app.camara is None:
            self.puente._enviar_telegram(chat_id, "La cámara no está disponible.")
            return

        frame = self.app.camara.capturar_fotograma()
        if frame is None:
            self.puente._enviar_telegram(chat_id, "No pude acceder a la cámara o no hay ninguna conectada.")
            if avisar_en_voz:
                self.app.cola.put(("hablar", "No pude acceder a la cámara."))
            return

        try:
            import cv2
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not ok:
                raise RuntimeError("Fallo al codificar JPEG")
            foto_bytes = buf.tobytes()
        except Exception as e:
            print(f"[telegram] Error codificando fotograma: {e}", flush=True)
            self.puente._enviar_telegram(chat_id, "Hubo un problema al preparar la foto de la cámara.")
            return

        ok = self.enviar_foto(chat_id, foto_bytes, caption="Aquí tienes la foto de la cámara.", tipo="camara")
        if ok and avisar_en_voz:
            self.app.cola.put(("hablar", "Te acabo de enviar la foto de la cámara a tu Telegram."))
