"""Puente de comunicación entre Telegram y Silvestra vía Telegram Bot API."""
import datetime
import random
import re
import threading
import time
import requests

import acciones
import config
import estado
import pantalla
from telegram_medios import GestorMediosTelegram


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


class TelegramPuente:
    def __init__(self, app):
        self.app = app
        self.token = getattr(config, "TOKEN_TELEGRAM", "").strip()
        self.activo = bool(self.token)
        self.id_dueno = int(getattr(config, "ID_TELEGRAM_DUENO", 0) or 0)
        self.chat_id_autorizado = self.id_dueno if self.id_dueno > 0 else estado.cargar().get("telegram_chat_id")
        self.codigo_pendiente = None
        self.tiempo_codigo = 0.0
        self.historial_proactivo = []
        self._hilo = None
        self._detener = threading.Event()
        self.medios = GestorMediosTelegram(self)
        if self.id_dueno <= 0:
            print("[telegram] AVISO: ID_TELEGRAM_DUENO es 0 o falta en config.py. El bot NO ejecutará acciones.", flush=True)

    def _guardar_chat_autorizado(self, chat_id):
        datos = estado.cargar()
        datos["telegram_chat_id"] = chat_id
        estado.guardar(datos)
        self.chat_id_autorizado = chat_id

    def iniciar(self):
        if not self.activo:
            print("[telegram] Desactivado (TOKEN_TELEGRAM no configurado en config.py)", flush=True)
            return
        self._detener.clear()
        self._hilo = threading.Thread(target=self._bucle_polling, daemon=True, name="TelegramPolling")
        self._hilo.start()
        print(f"[telegram] Puente iniciado. Chat autorizado: {self.chat_id_autorizado}", flush=True)

    def detener(self):
        self._detener.set()

    def _enviar_telegram(self, chat_id, texto):
        if not self.token or not chat_id:
            return False
        texto_seguro = sanitizar_privacidad(texto)
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            r = requests.post(url, json={"chat_id": chat_id, "text": texto_seguro}, timeout=10)
            if r.status_code == 200:
                print(f"[telegram] Mensaje enviado a chat_id={chat_id} (longitud={len(texto_seguro)})", flush=True)
                return True
            print(f"[telegram] Error enviando a chat_id={chat_id}: status={r.status_code}", flush=True)
        except Exception as e:
            print(f"[telegram] Excepción enviando a chat_id={chat_id}: {e}", flush=True)
        return False

    def enviar_audio(self, audio_bytes, caption=None):
        """Envía un audio MP3 a Telegram con sendAudio (sin requerir ffmpeg)."""
        if not self.token or not self.chat_id_autorizado or not audio_bytes:
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendAudio"
        files = {"audio": ("nota_voz.mp3", audio_bytes, "audio/mpeg")}
        data = {"chat_id": self.chat_id_autorizado, "title": "Nota de voz", "performer": "Silvestra"}
        if caption:
            data["caption"] = sanitizar_privacidad(caption)
        try:
            r = requests.post(url, files=files, data=data, timeout=30)
            if r.status_code == 200:
                print(f"[telegram] Audio enviado a chat_id={self.chat_id_autorizado} ({len(audio_bytes)} bytes)", flush=True)
                return True
            print(f"[telegram] Error enviando audio a chat_id={self.chat_id_autorizado}: status={r.status_code}", flush=True)
        except Exception as e:
            print(f"[telegram] Excepción enviando audio: {e}", flush=True)
        return False

    def avisar_celular(self, mensaje, forzar=False):
        """Envía un aviso proactivo respetando límite de 3/h y descanso (22:00-07:00)."""
        if not self.chat_id_autorizado:
            print("[telegram] Aviso proactivo descartado: sin chat vinculado.", flush=True)
            return False

        ahora = time.time()
        self.historial_proactivo = [t for t in self.historial_proactivo if ahora - t < 3600]

        if not forzar:
            if len(self.historial_proactivo) >= 3:
                print("[telegram] Aviso proactivo bloqueado: límite de 3 mensajes/hora alcanzado.", flush=True)
                return False
            hora = datetime.datetime.now().hour
            if hora >= 22 or hora < 7:
                print(f"[telegram] Aviso proactivo bloqueado: horario de silencio ({hora:02d}:00).", flush=True)
                return False

        ok = self._enviar_telegram(self.chat_id_autorizado, mensaje)
        if ok:
            self.historial_proactivo.append(ahora)
        return ok

    def _procesar_mensaje(self, msg):
        chat_id = msg.get("chat", {}).get("id")
        if chat_id is None:
            return

        id_dueno = int(getattr(config, "ID_TELEGRAM_DUENO", 0) or 0)
        if id_dueno <= 0:
            print(f"[telegram] AVISO: ID_TELEGRAM_DUENO no configurado. Mensaje ignorado de chat_id={chat_id}", flush=True)
            try:
                import control_seguridad
                control_seguridad.registrar_log("TELEGRAM", "mensaje_ignorado", f"id={chat_id}", "RECHAZADO", "ID_TELEGRAM_DUENO es 0 o falta")
            except Exception:
                pass
            return

        if chat_id != id_dueno:
            print(f"[telegram] Mensaje ignorado de usuario no autorizado: chat_id={chat_id}", flush=True)
            try:
                import control_seguridad
                control_seguridad.registrar_log("TELEGRAM", "mensaje_ignorado", f"id={chat_id}", "RECHAZADO", "Usuario no coincide con ID_TELEGRAM_DUENO")
            except Exception:
                pass
            return

        self.chat_id_autorizado = chat_id
        texto = msg.get("text", "")
        texto_limpio = (texto or "").strip()

        # 1. Notas de voz o audios entrantes
        if "voice" in msg or "audio" in msg:
            self.medios.procesar_nota_voz(msg)
            return

        # 2. Fotos entrantes (con o sin texto)
        if "photo" in msg:
            self.medios.procesar_foto(msg)
            return

        # 3. Texto normal
        if texto_limpio:
            self._atender_dueno(chat_id, texto_limpio)

    def _atender_dueno(self, chat_id, texto):
        print(f"[telegram] Mensaje recibido de dueño chat_id={chat_id} (longitud={len(texto)})", flush=True)
        if not texto:
            return

        self.app.origen_entrada_actual = "telegram"

        # Intercepción de código de seguridad antes del LLM
        if hasattr(self.app, "control_seguridad") and self.app.control_seguridad.tiene_pendiente():
            if self.app.control_seguridad.verificar_codigo(texto):
                return

        if hasattr(self.app, "cuidado") and self.app.cuidado:
            try:
                self.app.cuidado.notificar_senal_usuario("telegram", texto)
            except Exception:
                pass

        if hasattr(self.app, "propuestas") and self.app.propuestas:
            try:
                if self.app.propuestas.atender_respuesta_telegram(chat_id, texto):
                    return
                self.app.propuestas.detectar_desde_correccion(texto)
            except Exception:
                pass

        hablar_en_voz_alta = bool(re.search(r"\b(dilo en voz alta|en voz alta|leelo en voz alta|léelo en voz alta)\b", texto, re.I))

        try:
            resp, accion, *resto = self.app.cerebro.responder(texto)
        except Exception as e:
            print(f"[telegram] Error en cerebro: {e}", flush=True)
            self._enviar_telegram(chat_id, "Tuve un problema para procesar tu mensaje.")
            return

        # Manejo de captura de pantalla solicitada expresamente
        es_pedir_captura = bool(
            (accion and (accion.startswith("enviar_captura") or accion == "enviar_captura"))
            or re.search(r"\b(m[aá]ndame|env[ií]ame|p[aá]same)\b.*\b(captura|pantalla)\b", texto, re.I)
        )
        if es_pedir_captura:
            self._enviar_telegram(chat_id, sanitizar_privacidad(resp))
            self.medios.enviar_captura_pantalla(chat_id)
            return

        # Manejo de foto de cámara solicitada expresamente
        es_pedir_camara = bool(
            (accion and (accion.startswith("enviar_foto_camara") or accion == "enviar_foto_camara"))
            or re.search(r"\b(m[aá]ndame|env[ií]ame|toma|t[oó]mame|p[aá]same)\b.*\b(foto de la c[aá]mara|foto con la c[aá]mara|foto de c[aá]mara)\b", texto, re.I)
        )
        if es_pedir_camara:
            self._enviar_telegram(chat_id, sanitizar_privacidad(resp))
            self.medios.enviar_foto_camara(chat_id)
            return

        # Manejo de visión de pantalla sin enviar imágenes (solo texto)
        if accion and (accion.startswith("mirar_pantalla") or accion == "mirar_pantalla"):
            arg = accion.split("|", 1)[1].strip() if "|" in accion else None

            def al_terminar_vision(texto_vision):
                sani = sanitizar_privacidad(texto_vision)
                self._enviar_telegram(chat_id, sani)
                if hablar_en_voz_alta:
                    self.app.cola.put(("hablar", texto_vision))
                else:
                    self.app.cola.put(("telegram_burbuja", texto_vision))

            pantalla.analizar_pantalla(self.app, pregunta=arg, hablar=False, al_terminar=al_terminar_vision)
            return

        self._enviar_telegram(chat_id, sanitizar_privacidad(resp))
        if accion:
            self.app.cola.put(("ejecutar_accion", accion))

        if hablar_en_voz_alta:
            self.app.cola.put(("hablar", resp))
        else:
            self.app.cola.put(("telegram_burbuja", resp))

    def _bucle_polling(self):
        offset = 0
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"

        while not self._detener.is_set():
            try:
                params = {"offset": offset, "timeout": 20}
                r = requests.get(url, params=params, timeout=30)
                if r.status_code == 200:
                    datos = r.json()
                    if datos.get("ok"):
                        for update in datos.get("result", []):
                            offset = max(offset, update.get("update_id", 0) + 1)
                            msg = update.get("message") or update.get("edited_message")
                            if msg and msg.get("chat", {}).get("id") is not None:
                                self._procesar_mensaje(msg)
                elif r.status_code in (401, 404):
                    print(f"[telegram] Token inválido ({r.status_code}). Verifica config.py.", flush=True)
                    time.sleep(15)
                else:
                    time.sleep(3)
            except requests.exceptions.RequestException:
                time.sleep(5)
            except Exception as e:
                print(f"[telegram] Error en polling: {e}", flush=True)
                time.sleep(5)


def instalar(app):
    puente = TelegramPuente(app)

    def accion_avisar(arg=None):
        if arg:
            puente.avisar_celular(arg, forzar=True)

    def accion_captura(arg=None):
        if not puente.chat_id_autorizado:
            app.decir("No tienes ningún celular vinculado por Telegram para enviarte la captura.")
            return
        threading.Thread(target=puente.medios.enviar_captura_pantalla, args=(puente.chat_id_autorizado, True), daemon=True).start()

    def accion_camara(arg=None):
        if not puente.chat_id_autorizado:
            app.decir("No tienes ningún celular vinculado por Telegram para enviarte la foto.")
            return
        threading.Thread(target=puente.medios.enviar_foto_camara, args=(puente.chat_id_autorizado, True), daemon=True).start()

    acciones.registrar(
        "avisar_celular",
        accion_avisar,
        "envía un mensaje o recordatorio al celular de su dueño por Telegram. Escribe: ACCION: avisar_celular | mensaje",
        con_texto=True,
    )
    acciones.registrar(
        "enviar_captura",
        accion_captura,
        "captura la pantalla y la envía como foto al celular del dueño por Telegram (solo cuando él lo pida expresamente).",
    )
    acciones.registrar(
        "enviar_foto_camara",
        accion_camara,
        "toma una foto con la cámara y la envía al celular del dueño por Telegram (solo cuando él lo pida expresamente).",
    )

    puente.iniciar()
    return puente
