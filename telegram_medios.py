"""Procesamiento multimedia para el puente de Telegram de Silvestra.

Maneja notas de voz entrantes (Whisper + Edge-TTS), análisis de fotos con visión
multimodal y envío de capturas/cámara con filtros de privacidad y límites de seguridad.
Todo opera 100% en memoria (sin guardar archivos en disco).
"""
import base64
import io
import re
import threading
import time
import requests
from PIL import Image, ImageGrab

import config

MAX_BYTES_ARCHIVO = 10 * 1024 * 1024  # 10 MB
MAX_IMAGENES_HORA = 20


def sanitizar_privacidad(texto):
    """Elimina tokens, claves de API, rutas locales y archivos de configuración."""
    if not texto:
        return ""
    s = str(texto)
    s = re.sub(r"gsk_[A-Za-z0-9_-]{20,}", "[CLAVE_PROTEGIDA]", s)
    s = re.sub(r"sk-or-v1-[A-Za-z0-9_-]{20,}", "[CLAVE_PROTEGIDA]", s)
    s = re.sub(r"sk-[A-Za-z0-9_-]{20,}", "[CLAVE_PROTEGIDA]", s)
    s = re.sub(r"AQ\.[A-Za-z0-9_-]{20,}", "[CLAVE_PROTEGIDA]", s)
    s = re.sub(r"\d{8,12}:[A-Za-z0-9_-]{25,50}", "[TOKEN_PROTEGIDO]", s)
    s = re.sub(r"[A-Za-z]:\\[^\s\"'\n<>*|?]+", "[RUTA_LOCAL]", s)
    s = re.sub(r"/(?:[\w.-]+/)+[\w.-]+", "[RUTA_LOCAL]", s)
    s = re.sub(r"(?i)\bconfig\.py\b", "[configuración]", s)
    s = re.sub(r"(?i)\.env\b", "[configuración]", s)
    return s


def descargar_archivo_telegram(token, file_id, max_tam=MAX_BYTES_ARCHIVO):
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


def transcribir_audio(app, audio_bytes, nombre="nota.ogg"):
    """Transcribe un archivo de voz/audio en memoria usando Whisper de Groq."""
    try:
        r = app.cliente.audio.transcriptions.create(
            file=(nombre, audio_bytes),
            model=getattr(config, "MODELO_VOZ", "whisper-large-v3-turbo"),
            language="es",
            prompt="Conversación en español.",
            timeout=15.0,
        )
        return (r.text or "").strip()
    except Exception as e:
        print(f"[telegram_medios] Whisper falló: {e}", flush=True)
        return None


def _post_vision(url, clave, modelo, data_url, sistema, consulta, timeout=20):
    """Llamada a endpoints compatibles OpenAI para visión multimodal."""
    try:
        headers = {"Authorization": f"Bearer {clave}", "Content-Type": "application/json"}
        cuerpo = {
            "model": modelo,
            "messages": [
                {"role": "system", "content": sistema},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": consulta},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "max_tokens": 300,
            "temperature": 0.6,
        }
        r = requests.post(url, headers=headers, json=cuerpo, timeout=timeout)
        if r.status_code == 200:
            txt = r.json()["choices"][0]["message"].get("content")
            if txt:
                return txt.strip()
    except Exception as e:
        print(f"[telegram_medios] Visión en {modelo} falló: {e}", flush=True)
    return None


def _consultar_vision_multillm(app, data_url, sistema, consulta):
    """Consulta modelos de visión con failover: Groq -> Google Gemini -> OpenRouter."""
    # 1. Groq Vision
    modelos_groq = [config.MODELO_VISION] + [m for m in getattr(config, "MODELOS_VISION", []) if m != config.MODELO_VISION]
    for m in modelos_groq:
        try:
            r = app.cliente.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": sistema},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": consulta},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    },
                ],
                max_tokens=300,
                temperature=0.6,
                timeout=20.0,
            )
            if r.choices and r.choices[0].message.content:
                print(f"[tiempo] telegram_vision proveedor=Groq modelo={m}", flush=True)
                return r.choices[0].message.content.strip()
        except Exception as e:
            print(f"[telegram_medios] Groq vision {m} falló: {e}", flush=True)

    # 2. Respaldo Google Gemini
    clave_g = getattr(config, "CLAVE_GOOGLE", "").strip()
    if clave_g:
        url_g = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        for mod in ["gemini-flash-lite-latest", "gemini-3-flash-preview", "gemini-flash-latest"]:
            txt = _post_vision(url_g, clave_g, mod, data_url, sistema, consulta, 20)
            if txt:
                print(f"[tiempo] telegram_vision proveedor=Google modelo={mod}", flush=True)
                return txt

    # 3. Respaldo OpenRouter
    clave_or = getattr(config, "CLAVE_OPENROUTER", "").strip()
    if clave_or:
        url_or = "https://openrouter.ai/api/v1/chat/completions"
        txt = _post_vision(url_or, clave_or, "nvidia/nemotron-3.5-super-vl:free", data_url, sistema, consulta, 25)
        if txt:
            print(f"[tiempo] telegram_vision proveedor=OpenRouter", flush=True)
            return txt
    return None


def analizar_imagen_vision(app, foto_bytes, pregunta=None):
    """Reduce la imagen en memoria y consulta al modelo de visión."""
    try:
        img = Image.open(io.BytesIO(foto_bytes))
        max_dim = 1280
        if img.width > max_dim or img.height > max_dim:
            esc = min(max_dim / img.width, max_dim / img.height)
            img = img.resize((max(1, int(img.width * esc)), max(1, int(img.height * esc))), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=70)
        data_url = f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
    except Exception as e:
        print(f"[telegram_medios] Error procesando imagen en memoria: {e}", flush=True)
        return "No pude abrir o procesar la imagen enviada."

    consulta = (pregunta or "").strip() or "describe esta imagen y dime si ves algún problema"
    nombre = getattr(app.memoria, "nombre", "Silvestra")
    creador = getattr(app.memoria, "creador", "Moisés")
    sistema = (
        f"Eres {nombre}, asistente creada por {creador} en Panamá.\n"
        "Estás viendo una imagen que te enviaron por Telegram.\n"
        "Responde de forma concisa, cálida y natural en español de Panamá (1 a 3 frases).\n"
        "Regla de privacidad: jamás leas ni repitas contraseñas, claves, tokens ni números de tarjetas visibles en la foto."
    )
    resp = _consultar_vision_multillm(app, data_url, sistema, consulta)
    if not resp:
        return "No pude analizar la imagen en este momento, por favor intenta de nuevo."
    return resp.replace("*", "").replace("- ", "").replace("\n", " ").strip("\"' ")


def verificar_privacidad_pantalla(app, b64_jpeg):
    """Comprueba si una captura de pantalla contiene claves o contraseñas visibles."""
    sistema = (
        "Eres un analizador estricto de seguridad informática y privacidad.\n"
        "Revisa la captura de pantalla y determina si muestra contraseñas, claves secretas, "
        "tokens de autenticación (gsk_, sk-, etc.) o datos confidenciales expuestos en texto claro.\n"
        "Regla obligatoria: si detectas contraseñas o claves secretas visibles, responde exactamente: PRIVADO: <motivo breve>.\n"
        "Si no contiene ninguna contraseña ni clave secreta expuesta, responde exactamente: SEGURO."
    )
    res = _consultar_vision_multillm(
        app,
        f"data:image/jpeg;base64,{b64_jpeg}",
        sistema,
        "¿Contiene esta pantalla contraseñas o claves secretas expuestas?",
    )
    if res and res.upper().startswith("PRIVADO"):
        print(f"[telegram] Captura de pantalla bloqueada por privacidad: {res}", flush=True)
        return False
    return True


class GestorMediosTelegram:
    """Administra recepción de notas de voz, fotos y envío de capturas/cámara."""

    def __init__(self, puente):
        self.puente = puente
        self.app = puente.app
        self.historial_imagenes_enviadas = []
        self._bloqueo_limite = threading.Lock()

    def _puede_enviar_imagen(self):
        """Aplica la cuota de máximo 20 imágenes enviadas por hora."""
        with self._bloqueo_limite:
            ahora = time.time()
            self.historial_imagenes_enviadas = [t for t in self.historial_imagenes_enviadas if ahora - t < 3600]
            if len(self.historial_imagenes_enviadas) >= MAX_IMAGENES_HORA:
                return False
            self.historial_imagenes_enviadas.append(ahora)
            return True

    def enviar_foto(self, chat_id, foto_bytes, caption=None, tipo="imagen"):
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
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = sanitizar_privacidad(caption)

        try:
            r = requests.post(url, files=files, data=data, timeout=30)
            if r.status_code == 200:
                print(f"[telegram] Imagen enviada tipo={tipo} chat_id={chat_id} ({len(foto_bytes)} bytes, sin guardar en disco)", flush=True)
                return True
            print(f"[telegram] Error enviando imagen tipo={tipo}: status={r.status_code}", flush=True)
        except Exception as e:
            print(f"[telegram] Excepción enviando imagen tipo={tipo}: {e}", flush=True)
        return False

    def procesar_nota_voz(self, msg):
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

        # Seguridad: la nota de voz es pregunta conversacional, no ejecuta órdenes de sistema
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

    def procesar_foto(self, msg):
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

    def enviar_captura_pantalla(self, chat_id, avisar_en_voz=False):
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

        if not verificar_privacidad_pantalla(self.app, b64):
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

    def enviar_foto_camara(self, chat_id, avisar_en_voz=False):
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
