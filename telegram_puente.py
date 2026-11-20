"""Puente de comunicación entre Telegram y Silvestra vía Telegram Bot API nativa."""
import datetime
import json
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# Forzar resolución IPv4 nativa para telegram.org
_orig_gai = socket.getaddrinfo
def _ipv4_gai(h, p, f=0, t=0, pr=0, fl=0):
    return _orig_gai(h, p, socket.AF_INET if h and "telegram.org" in str(h) else f, t, pr, fl)
socket.getaddrinfo = _ipv4_gai

_SSL_CTX = ssl.create_default_context()

import acciones
import config
import estado
import pantalla
from telegram_medios import GestorMediosTelegram, sanitizar_privacidad


class TelegramPuente:
    def __init__(self, app):
        self.app = app
        self.token = getattr(config, "TOKEN_TELEGRAM", "").strip()
        self.activo = bool(self.token)
        self.id_dueno = int(getattr(config, "ID_TELEGRAM_DUENO", 0) or 0)
        self.chat_id_autorizado = self.id_dueno if self.id_dueno > 0 else estado.cargar().get("telegram_chat_id")
        self.historial_proactivo = []
        self._hilo = None
        self._detener = threading.Event()
        self.medios = GestorMediosTelegram(self)
        if self.id_dueno <= 0:
            print("[telegram] AVISO: ID_TELEGRAM_DUENO es 0 o falta en config.py. El bot NO ejecutará acciones.", flush=True)

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
        payload = json.dumps({"chat_id": chat_id, "text": texto_seguro}).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "Silvestra/1.0", "Connection": "close"}

        for intento in range(2):
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
                    if resp.status == 200:
                        datos = json.loads(resp.read().decode("utf-8"))
                        if datos.get("ok"):
                            print(f"[telegram] Mensaje enviado a chat_id={chat_id} (longitud={len(texto_seguro)})", flush=True)
                            return True
                    return False
            except (socket.timeout, TimeoutError) as e:
                print(f"[telegram] Timeout en sendMessage (sin reintentar para no duplicar): {e}", flush=True)
                return False
            except urllib.error.URLError as e:
                err_s = str(e.reason).lower() if hasattr(e, "reason") else str(e).lower()
                if "timed out" in err_s:
                    print(f"[telegram] Timeout en sendMessage (sin reintentar para no duplicar): {e}", flush=True)
                    return False
                print(f"[telegram] Error de conexión en sendMessage (intento {intento + 1}/2): {e}", flush=True)
                if intento == 0:
                    time.sleep(1.0)
            except Exception as e:
                print(f"[telegram] Excepción enviando a chat_id={chat_id}: {e}", flush=True)
                return False
        return False

    def enviar_audio(self, audio_bytes, caption=None):
        """Envía un audio MP3 a Telegram con sendAudio (sin requerir ffmpeg)."""
        if not self.token or not self.chat_id_autorizado or not audio_bytes:
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendAudio"
        boundary = f"----SilvestraBoundary{int(time.time()*1000)}"
        c_disp = f"--{boundary}\r\nContent-Disposition: form-data; name="
        body = bytearray()
        for k, v in [("chat_id", str(self.chat_id_autorizado)), ("title", "Nota de voz"), ("performer", "Silvestra")]:
            body.extend(f'{c_disp}"{k}"\r\n\r\n{v}\r\n'.encode("utf-8"))
        if caption:
            body.extend(f'{c_disp}"caption"\r\n\r\n{sanitizar_privacidad(caption)}\r\n'.encode("utf-8"))
        body.extend(
            f'{c_disp}"audio"; filename="nota_voz.mp3"\r\nContent-Type: audio/mpeg\r\n\r\n'.encode("utf-8")
            + audio_bytes + b"\r\n" + f"--{boundary}--\r\n".encode("utf-8")
        )
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "Silvestra/1.0", "Connection": "close"}
        req = urllib.request.Request(url, data=bytes(body), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
                if resp.status == 200:
                    datos = json.loads(resp.read().decode("utf-8"))
                    if datos.get("ok"):
                        print(f"[telegram] Audio enviado a chat_id={self.chat_id_autorizado} ({len(audio_bytes)} bytes)", flush=True)
                        return True
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
        if id_dueno <= 0 or chat_id != id_dueno:
            motivo = "ID_TELEGRAM_DUENO no configurado" if id_dueno <= 0 else "Usuario no autorizado"
            print(f"[telegram] Mensaje ignorado de chat_id={chat_id}: {motivo}", flush=True)
            try:
                import control_seguridad
                control_seguridad.registrar_log("TELEGRAM", "mensaje_ignorado", f"id={chat_id}", "RECHAZADO", motivo)
            except Exception:
                pass
            return

        self.chat_id_autorizado = chat_id
        texto_limpio = (msg.get("text") or "").strip()

        if "voice" in msg or "audio" in msg:
            self.medios.procesar_nota_voz(msg)
        elif "photo" in msg:
            import camara_dueno
            if camara_dueno.es_foto_entrenamiento_cara(msg.get("caption", "")):
                self._procesar_entrenamiento_cara(msg)
            else:
                self.medios.procesar_foto(msg)
        elif texto_limpio:
            self._atender_dueno(chat_id, texto_limpio)

    def _atender_dueno(self, chat_id, texto):
        print(f"[telegram] Mensaje recibido de dueño chat_id={chat_id} (longitud={len(texto)})", flush=True)
        if not texto:
            return
        self.app.origen_entrada_actual = "telegram"

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

        if (accion and accion.startswith("enviar_captura")) or re.search(r"\b(m[aá]ndame|env[ií]ame|p[aá]same)\b.*\b(captura|pantalla)\b", texto, re.I):
            self._enviar_telegram(chat_id, sanitizar_privacidad(resp))
            self.medios.enviar_captura_pantalla(chat_id)
            return

        if (accion and accion.startswith("enviar_foto_camara")) or re.search(r"\b(m[aá]ndame|env[ií]ame|toma|t[oó]mame|p[aá]same)\b.*\bfoto.*c[aá]mara\b", texto, re.I):
            self._enviar_telegram(chat_id, sanitizar_privacidad(resp))
            self.medios.enviar_foto_camara(chat_id)
            return

        if accion and (accion.startswith("mirar_pantalla") or accion == "mirar_pantalla"):
            arg = accion.split("|", 1)[1].strip() if "|" in accion else None

            def al_terminar_vision(texto_vision):
                sani = sanitizar_privacidad(texto_vision)
                self._enviar_telegram(chat_id, sani)
                self.app.cola.put(("hablar" if hablar_en_voz_alta else "telegram_burbuja", texto_vision))

            pantalla.analizar_pantalla(self.app, pregunta=arg, hablar=False, al_terminar=al_terminar_vision)
            return

        self._enviar_telegram(chat_id, sanitizar_privacidad(resp))
        if accion:
            self.app.cola.put(("ejecutar_accion", accion))
        self.app.cola.put(("hablar" if hablar_en_voz_alta else "telegram_burbuja", resp))

    def _procesar_entrenamiento_cara(self, msg):
        chat_id = msg.get("chat", {}).get("id")
        fotos = msg.get("photo", [])
        if not fotos or not fotos[-1].get("file_id"):
            return
        from telegram_medios import descargar_archivo_telegram
        bytes_foto, err = descargar_archivo_telegram(self.token, fotos[-1]["file_id"])
        if err or not bytes_foto:
            self._enviar_telegram(chat_id, "No pude descargar la foto enviada.")
            return
        import camara_dueno
        ok, mensaje, n = camara_dueno.aprender_cara_desde_bytes(bytes_foto)
        if ok and hasattr(self.app, "camara") and self.app.camara:
            try:
                self.app.camara.recargar_banco_dueno()
            except Exception as e:
                print(f"[telegram] Error recargando banco en camara: {e}", flush=True)
        self._enviar_telegram(chat_id, f"{'✅' if ok else '⚠️'} {mensaje}")
        if ok:
            self.app.cola.put(("telegram_burbuja", f"[Foto aprendida]: {mensaje}"))

    def _bucle_polling(self):
        offset = 0
        base_url = f"https://api.telegram.org/bot{self.token}/getUpdates"

        while not self._detener.is_set():
            try:
                query = urllib.parse.urlencode({"offset": offset, "timeout": 20})
                url = f"{base_url}?{query}"
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Silvestra/1.0", "Connection": "close"}
                )
                with urllib.request.urlopen(req, timeout=25, context=_SSL_CTX) as resp:
                    if resp.status == 200:
                        datos = json.loads(resp.read().decode("utf-8"))
                        if datos.get("ok"):
                            for update in datos.get("result", []):
                                offset = max(offset, update.get("update_id", 0) + 1)
                                msg = update.get("message") or update.get("edited_message")
                                if msg and msg.get("chat", {}).get("id") is not None:
                                    self._procesar_mensaje(msg)
            except urllib.error.HTTPError as e:
                if e.code in (401, 404):
                    print(f"[telegram] Token inválido ({e.code}). Verifica config.py.", flush=True)
                    time.sleep(15)
                else:
                    time.sleep(3)
            except (socket.timeout, TimeoutError):
                pass
            except urllib.error.URLError as e:
                if isinstance(e.reason, (socket.timeout, TimeoutError)) or "timed out" in str(e.reason).lower():
                    pass
                else:
                    time.sleep(5)
            except Exception as e:
                print(f"[telegram] Error en polling: {e}", flush=True)
                time.sleep(5)


def instalar(app):
    puente = TelegramPuente(app)

    def accion_avisar(arg=None):
        if arg:
            threading.Thread(
                target=lambda: puente.avisar_celular(arg, forzar=True) or app.cola.put(("frase", "No pude enviar el mensaje a Telegram.")),
                daemon=True,
                name="TelegramAvisar"
            ).start()

    def _lanza(metodo, msg_err):
        if not puente.chat_id_autorizado:
            app.decir(msg_err)
        else:
            threading.Thread(target=metodo, args=(puente.chat_id_autorizado, True), daemon=True).start()

    acciones.registrar("avisar_celular", accion_avisar, "envía mensaje al celular por Telegram. Escribe: ACCION: avisar_celular | mensaje", con_texto=True)
    acciones.registrar("enviar_mensaje_telegram", accion_avisar, "envía mensaje a Telegram. Escribe: ACCION: enviar_mensaje_telegram | mensaje", con_texto=True)
    acciones.registrar("enviar_captura", lambda arg=None: _lanza(puente.medios.enviar_captura_pantalla, "No tienes ningún celular vinculado por Telegram para enviarte la captura."), "captura la pantalla y la envía por Telegram.")
    acciones.registrar("enviar_foto_camara", lambda arg=None: _lanza(puente.medios.enviar_foto_camara, "No tienes ningún celular vinculado por Telegram para enviarte la foto."), "toma foto con cámara y la envía por Telegram.")

    puente.iniciar()
    return puente
