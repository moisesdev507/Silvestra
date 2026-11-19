import asyncio
import datetime
import re
import threading
import time

import acciones
import estado
import proveedores
from telegram_puente import sanitizar_privacidad


def sintetizar_audio_mp3(texto, emocion="preocupada"):
    try:
        import edge_tts
        from voz import normalizar_emocion, EMOCIONES_VOZ
        emo = normalizar_emocion(emocion)
        ajustes = EMOCIONES_VOZ.get(emo) or EMOCIONES_VOZ.get("preocupada", {"rate": "-8%", "pitch": "-4Hz", "volume": "-5%"})
        rate = ajustes.get("rate", "-8%")
        pitch = ajustes.get("pitch", "-4Hz")
        volume = ajustes.get("volume", "-5%")
        print(f"[voz] emocion={emo} rate={rate} pitch={pitch}", flush=True)
        async def _crear():
            datos = bytearray()
            async for t in edge_tts.Communicate(texto, "es-PA-MargaritaNeural", rate=rate, pitch=pitch, volume=volume).stream():
                if t.get("type") == "audio":
                    datos += t.get("data", b"")
            return bytes(datos)
        return asyncio.run(asyncio.wait_for(_crear(), 12))
    except Exception as e:
        print(f"[cuidado] Error audio: {e}", flush=True)
        return None


def parsear_hora_regreso(arg):
    if not arg:
        return None, None
    s = arg.lower().strip()
    ahora = datetime.datetime.now()
    m_min = re.search(r"en\s+(\d+)\s*(?:minutos?|mins?)", s)
    if m_min:
        t = ahora + datetime.timedelta(minutes=int(m_min.group(1)))
        return t.timestamp(), t.strftime("%H:%M")
    m_h = re.search(r"en\s+(\d+)\s+horas?", s)
    if m_h:
        t = ahora + datetime.timedelta(hours=int(m_h.group(1)))
        return t.timestamp(), t.strftime("%H:%M")
    m_hora = re.search(r"(?:a\s+las\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
    if m_hora:
        h, m, mer = int(m_hora.group(1)), int(m_hora.group(2) or 0), m_hora.group(3)
        if mer == "pm" and h < 12:
            h += 12
        elif mer == "am" and h == 12:
            h = 0
        elif not mer and h <= 6 and (ahora.hour >= 12 or h < ahora.hour):
            h += 12
        if 0 <= h <= 23 and 0 <= m <= 59:
            t = ahora.replace(hour=h, minute=m, second=0, microsecond=0)
            if t <= ahora:
                t += datetime.timedelta(days=1)
            return t.timestamp(), t.strftime("%H:%M")
    return None, None


class Cuidado:
    def __init__(self, app):
        self.app = app
        self._bloqueo = threading.RLock()
        self._detener = threading.Event()
        self.salida = estado.cargar().get("salida_activa")
        self._hilo = threading.Thread(target=self._bucle_chequeo, daemon=True, name="CuidadoLoop")
        self._hilo.start()

    def guardar_estado(self):
        datos = estado.cargar()
        datos["salida_activa"] = self.salida
        estado.guardar(datos)

    def registrar_salida(self, arg):
        creador = getattr(self.app.memoria, "creador", "Moisés") or "Moisés"
        ts, hora_str = parsear_hora_regreso(arg)
        with self._bloqueo:
            if not ts:
                self.salida = {"activa": False, "esperando_hora": True, "hora_salida": time.time()}
                self.guardar_estado()
                return f"¿A qué hora piensas volver, {creador}?"
            h_dt = datetime.datetime.fromtimestamp(ts)
            self.salida = {"activa": True, "esperando_hora": False, "hora_regreso": hora_str, "timestamp_regreso": ts, "hora_salida": time.time(), "chequeos_enviados": 0, "permite_madrugada": (h_dt.hour >= 22 or h_dt.hour < 7)}
            self.guardar_estado()
        print(f"[cuidado] Salida registrada: {hora_str}", flush=True)
        return f"Que te vaya muy bien, {creador}. Aquí estaré pendiente a las {hora_str}."

    def cancelar_salida(self, motivo="regreso"):
        creador = getattr(self.app.memoria, "creador", "Moisés") or "Moisés"
        with self._bloqueo:
            if not self.salida or not (self.salida.get("activa") or self.salida.get("esperando_hora")):
                return None
            self.salida = None
            self.guardar_estado()
        return f"¡Qué bueno tenerte de vuelta, {creador}! Me alegra saber que estás bien."

    def notificar_senal_usuario(self, origen="laptop", texto=""):
        t = (texto or "").lower().strip()
        regreso = ["estoy bien", "ya volví", "ya volvi", "ya regresé", "ya regrese", "ya llegué", "ya llegue", "todo bien", "tranquila", "cancela la salida"]
        es_regreso = any(p in t for p in regreso)
        with self._bloqueo:
            if not self.salida:
                return
            if self.salida.get("esperando_hora"):
                ts, hora_str = parsear_hora_regreso(texto)
                if ts:
                    h_dt = datetime.datetime.fromtimestamp(ts)
                    self.salida = {"activa": True, "esperando_hora": False, "hora_regreso": hora_str, "timestamp_regreso": ts, "hora_salida": time.time(), "chequeos_enviados": 0, "permite_madrugada": (h_dt.hour >= 22 or h_dt.hour < 7)}
                    self.guardar_estado()
                    self.app.cola.put(("hablar", f"Anotado, {getattr(self.app.memoria, 'creador', 'Moisés')}. Estaré pendiente a las {hora_str}."))
                    return

            if self.salida.get("activa"):
                ahora = time.time()
                ts_reg = self.salida.get("timestamp_regreso", 0)
                if es_regreso or ahora >= (ts_reg - 300):
                    resp = self.cancelar_salida("señal: " + origen)
                    if resp:
                        self.app.cola.put(("hablar", resp))
                        puente = getattr(self.app, "telegram", None)
                        if puente and origen == "telegram":
                            puente.avisar_celular(resp, forzar=True)

    def enviar_nota_voz(self, texto):
        if not texto:
            return "No me dijiste qué decir en la nota de voz."
        puente = getattr(self.app, "telegram", None)
        if not puente or not getattr(puente, "chat_id_autorizado", None):
            return "No tengo Telegram emparejado para mandar notas de voz."
        txt_sani = sanitizar_privacidad(texto)
        audio = sintetizar_audio_mp3(txt_sani)
        if not audio:
            return "No pude generar el audio de la nota de voz."
        ok = puente.enviar_audio(audio, caption=txt_sani)
        return "Nota de voz enviada a tu Telegram." if ok else "No pude enviar el audio por Telegram."

    def _generar_mensaje_chequeo(self, paso, hora_regreso):
        creador = getattr(self.app.memoria, "creador", "Moisés") or "Moisés"
        fallbacks = {
            1: f"{creador}, ya pasaron 20 minutos de las {hora_regreso}, ¿todo bien?",
            2: f"{creador}, van 40 minutos de las {hora_regreso}. Avísame cuando puedas.",
            3: f"{creador}, ya pasó una hora de tu regreso. Avísame con calma.",
        }
        try:
            resp = proveedores.completar([
                {"role": "system", "content": f"Eres Silvestra, asistente de {creador}. Dijo que volvía a las {hora_regreso} y está retrasado. Escribe 1 o 2 frases cariñosas para saber si está bien. Cero reproches ni culpas."},
                {"role": "user", "content": f"Paso {paso}"}
            ], tarea="fondo")
            if resp and resp.strip():
                return sanitizar_privacidad(resp.replace("*", "").replace("\n", " ").strip(" \"'"))
        except Exception:
            pass
        return fallbacks.get(paso, fallbacks[1])

    def _ejecutar_chequeo(self, paso, hora_regreso):
        puente = getattr(self.app, "telegram", None)
        tiene_tel = bool(puente and getattr(puente, "chat_id_autorizado", None))
        msg = self._generar_mensaje_chequeo(paso, hora_regreso)
        print(f"[cuidado] Chequeo paso {paso}: {msg}", flush=True)
        if not tiene_tel:
            return
        if paso == 2:
            audio = sintetizar_audio_mp3(msg)
            if audio and puente.enviar_audio(audio, caption=msg):
                return
        puente.avisar_celular(msg, forzar=True)

    def _bucle_chequeo(self):
        while not self._detener.is_set():
            try:
                ahora = time.time()
                camara = getattr(self.app, "camara", None)
                ult_d = getattr(camara, "ult_dueno", 0) if camara else 0
                if isinstance(ult_d, (int, float)) and ult_d > 0 and ahora - ult_d < 15:
                    self.notificar_senal_usuario("camara", "dueño presente")

                with self._bloqueo:
                    sal = self.salida

                if sal and sal.get("activa"):
                    delta = ahora - sal.get("timestamp_regreso", 0)
                    h_reg = sal.get("hora_regreso", "la hora prevista")
                    env = sal.get("chequeos_enviados", 0)
                    hora_act = datetime.datetime.now().hour
                    madrugada = (hora_act >= 22 or hora_act < 7)

                    if not madrugada or sal.get("permite_madrugada"):
                        paso_actual = 1 if (delta >= 1200 and env == 0) else (2 if (delta >= 2400 and env == 1) else (3 if (delta >= 3600 and env == 2) else 0))
                        if paso_actual:
                            self._ejecutar_chequeo(paso_actual, h_reg)
                            with self._bloqueo:
                                if self.salida:
                                    self.salida["chequeos_enviados"] = paso_actual
                                    self.guardar_estado()
            except Exception as e:
                print(f"[cuidado] Error bucle: {e}", flush=True)
            time.sleep(10)


def instalar(app):
    cui = Cuidado(app)
    acciones.registrar("registrar_salida", lambda arg=None: app.cola.put(("hablar", cui.registrar_salida(arg))), "anota salida y hora estimada de regreso. Escribe: ACCION: registrar_salida | hora", con_texto=True)
    acciones.registrar("cancelar_salida", lambda arg=None: app.cola.put(("hablar", cui.cancelar_salida("orden") or "No tenías salida activa.")), "cancela salida y confirma regreso")
    acciones.registrar("enviar_nota_voz", lambda arg=None: app.cola.put(("hablar", cui.enviar_nota_voz(arg))), "envía nota de voz a Telegram. Escribe: ACCION: enviar_nota_voz | mensaje", con_texto=True)
    acciones.registrar("probar_chequeo", lambda arg=None: cui._ejecutar_chequeo(int(arg) if arg and arg.strip() in ("1", "2", "3") else 1, "la prueba"), "prueba chequeo (1, 2 o 3)", con_texto=True)
    return cui
