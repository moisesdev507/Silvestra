"""Gestión persistente de recordatorios y alarmas para Silvestra en recordatorios.json."""
import datetime
import json
import os
import re
import threading
import time

import acciones
import persistencia_segura as ps

RUTA_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordatorios.json")
_bloqueo_disco = threading.RLock()


def _obtener_tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("America/Panama")
    except Exception:
        return None


def _ahora_tz():
    tz = _obtener_tz()
    return datetime.datetime.now(tz) if tz else datetime.datetime.now()


def _cargar():
    with _bloqueo_disco:
        res = ps.cargar_json_seguro(RUTA_JSON, [])
        return res if isinstance(res, list) else []


def _guardar(datos):
    with _bloqueo_disco:
        return ps.guardar_json_atomico(RUTA_JSON, datos if isinstance(datos, list) else [])


def formatear_hora_es(dt):
    """Formatea una hora en formato de 12 horas panameño con a. m. / p. m."""
    h = dt.hour % 12 or 12
    m = f"{dt.minute:02d}"
    mer = "p. m." if dt.hour >= 12 else "a. m."
    return f"{h}:{m} {mer}"


def parsear_tiempo(arg):
    """Interpreta expresiones relativas y absolutas con hora de Panamá."""
    if not arg or not str(arg).strip():
        return None, None, None
    arg = str(arg).strip()
    ahora = _ahora_tz()

    # Extraer tiempo_str y texto
    if "|" in arg:
        partes = arg.split("|", 1)
        tiempo_str = partes[0].strip().lower()
        texto = partes[1].strip()
    else:
        # Extraer patrón temporal del inicio o en medio de la frase
        m_t = re.search(
            r"(?:(?:en\s+)?\d+\s*(?:minutos?|mins?|segundos?|horas?|h\b)|"
            r"mañana(?:\s+a\s+las)?\s+\d+(?::\d+)?(?:\s*(?:am|pm|a\.?\s*m\.?|p\.?\s*m\.?))?|"
            r"a\s+las\s+\d+(?::\d+)?(?:\s*(?:am|pm|a\.?\s*m\.?|p\.?\s*m\.?))?)",
            arg,
            re.I,
        )
        if m_t:
            tiempo_str = m_t.group(0).strip().lower()
            resto = (arg[:m_t.start()] + " " + arg[m_t.end():]).strip()
            resto = re.sub(
                r"\b(avísame|avisame|recuérdame|recuerdame|pon(?:er)?\s+recordatorio|recordar|que\s+tengo\s+que|que|de\s+que|de|para|sobre)\b",
                "",
                resto,
                flags=re.I,
            ).strip()
            texto = resto or "lo que me pediste"
        else:
            tiempo_str = arg.lower()
            texto = "lo que me pediste"

    # 1. Mañana a las H[:M] [am|pm]
    m_man = re.search(r"mañana(?:\s+a\s+las)?\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.?\s*m\.?|p\.?\s*m\.?)?", tiempo_str)
    if m_man:
        h = int(m_man.group(1))
        m = int(m_man.group(2) or 0)
        mer = (m_man.group(3) or "").replace(".", "").replace(" ", "")
        if mer == "pm" and h < 12:
            h += 12
        elif mer == "am" and h == 12:
            h = 0
        target = ahora.replace(hour=h, minute=m, second=0, microsecond=0) + datetime.timedelta(days=1)
        return target.timestamp(), f"mañana a las {formatear_hora_es(target)}", texto

    # 2. Relativo: en X minutos / segundos / horas
    m_rel = re.search(r"(?:en\s+)?(\d+)\s*(minutos?|mins?|segundos?|segs?|horas?|h\b)", tiempo_str)
    if m_rel:
        val = int(m_rel.group(1))
        unidad = m_rel.group(2)
        if "seg" in unidad:
            delta = datetime.timedelta(seconds=val)
        elif "hora" in unidad or unidad == "h":
            delta = datetime.timedelta(hours=val)
        else:
            delta = datetime.timedelta(minutes=val)
        target = ahora + delta
        return target.timestamp(), formatear_hora_es(target), texto

    # 3. Absoluto hoy o próximo: a las H[:M] [am|pm]
    m_hora = re.search(r"(?:a\s+las\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.?\s*m\.?|p\.?\s*m\.?)?", tiempo_str)
    if m_hora:
        h = int(m_hora.group(1))
        m = int(m_hora.group(2) or 0)
        mer = (m_hora.group(3) or "").replace(".", "").replace(" ", "")
        if mer == "pm" and h < 12:
            h += 12
        elif mer == "am" and h == 12:
            h = 0
        if 0 <= h <= 23 and 0 <= m <= 59:
            target = ahora.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= ahora:
                target += datetime.timedelta(days=1)
            prefijo = "mañana a las " if target.day != ahora.day else ""
            return target.timestamp(), f"{prefijo}{formatear_hora_es(target)}", texto

    return None, None, texto


class Recordatorios:
    def __init__(self, app):
        self.app = app
        self._bloqueo = threading.RLock()
        self._detener = threading.Event()
        self.verificar_arranque()

        self._hilo = threading.Thread(target=self._bucle, daemon=True, name="RecordatoriosLoop")
        self._hilo.start()

    def verificar_arranque(self):
        """Revisa recordatorios pendientes al encender y avisa de los vencidos."""
        creador = getattr(getattr(self.app, "memoria", None), "creador", "Moisés") or "Moisés"
        ahora_ts = time.time()
        with self._bloqueo:
            datos = _cargar()
            vencidos = []
            for r in datos:
                if not r.get("completado") and r.get("timestamp", 0) <= ahora_ts:
                    r["completado"] = True
                    vencidos.append(r)
            if vencidos:
                _guardar(datos)
                for v in vencidos:
                    txt = v.get("texto", "")
                    aviso = f"{creador}, mientras estaba apagada venció este recordatorio: {txt}."
                    print(f"[recordatorio] vencido_arranque='{txt}'", flush=True)
                    if hasattr(self.app, "cola") and self.app.cola:
                        self.app.cola.put(("hablar_registro", (aviso, f"⏰ RECORDATORIO VENCIDO:\n{txt}")))

    def poner_recordatorio(self, arg):
        """Agrega un recordatorio relativo o absoluto y devuelve confirmación con hora exacta."""
        if not arg or not str(arg).strip():
            arg = getattr(self.app, "ultimo_texto_usuario", None) or getattr(
                getattr(self.app, "cerebro", None), "ultimo_texto_usuario", ""
            )

        ts, hora_str, texto = parsear_tiempo(arg)
        if not ts:
            return "No entendí la hora o el tiempo para el recordatorio. Puedes decir por ejemplo 'en 20 minutos' o 'mañana a las 8'."

        creador = getattr(getattr(self.app, "memoria", None), "creador", "Moisés") or "Moisés"
        tz = _obtener_tz()
        dt_target = datetime.datetime.fromtimestamp(ts, tz) if tz else datetime.datetime.fromtimestamp(ts)
        item = {
            "id": int(time.time() * 1000),
            "texto": texto,
            "timestamp": ts,
            "hora_exacta": hora_str,
            "fecha": dt_target.strftime("%Y-%m-%d"),
            "completado": False,
        }
        with self._bloqueo:
            datos = _cargar()
            datos.append(item)
            _guardar(datos)

        print(f"[recordatorio] creado='{texto}' hora='{hora_str}'", flush=True)
        return f"Listo, {creador}. Te recordaré {texto} a las {hora_str}."

    def listar_recordatorios(self):
        """Devuelve la lista hablada de recordatorios pendientes."""
        creador = getattr(getattr(self.app, "memoria", None), "creador", "Moisés") or "Moisés"
        with self._bloqueo:
            datos = _cargar()
            pendientes = [r for r in datos if not r.get("completado")]

        if not pendientes:
            return f"{creador}, no tienes ningún recordatorio pendiente."

        items = [f"{r['texto']} ({r['hora_exacta']})" for r in pendientes]
        return f"{creador}, tienes {len(pendientes)} recordatorio(s) pendiente(s): " + "; ".join(items) + "."

    def cancelar_recordatorio(self, arg):
        """Cancela un recordatorio pendiente que coincida con el texto indicado."""
        if not arg or not arg.strip():
            return "Dime qué recordatorio quieres que cancele."
        t_busca = arg.strip().lower()

        with self._bloqueo:
            datos = _cargar()
            cancelado = None
            for r in datos:
                if not r.get("completado") and t_busca in r.get("texto", "").lower():
                    r["completado"] = True
                    cancelado = r
                    break
            if cancelado:
                _guardar(datos)
                txt = cancelado.get("texto", "")
                print(f"[recordatorio] cancelado='{txt}'", flush=True)
                return f"Listo. Cancelé el recordatorio: '{txt}'."
        return f"No encontré ningún recordatorio pendiente sobre '{arg}'."

    def _bucle(self):
        """Revisa cada segundo si vence algún recordatorio."""
        while not self._detener.is_set():
            try:
                ahora_ts = time.time()
                creador = getattr(getattr(self.app, "memoria", None), "creador", "Moisés") or "Moisés"
                vencidos = []
                with self._bloqueo:
                    datos = _cargar()
                    cambios = False
                    for r in datos:
                        if not r.get("completado") and ahora_ts >= r.get("timestamp", 0):
                            r["completado"] = True
                            vencidos.append(r)
                            cambios = True
                    if cambios:
                        _guardar(datos)

                for r in vencidos:
                    txt = r.get("texto", "")
                    aviso = f"{creador}, te recuerdo: {txt}."
                    print(f"[recordatorio] disparado='{txt}'", flush=True)
                    if hasattr(self.app, "cola") and self.app.cola:
                        self.app.cola.put(("hablar_registro", (aviso, f"⏰ RECORDATORIO:\n{txt}")))
                    puente = getattr(self.app, "telegram", None)
                    if puente and getattr(puente, "chat_id_autorizado", None):
                        puente.avisar_celular(f"🔔 Recordatorio: {txt}", forzar=True)

            except Exception as e:
                print(f"[recordatorios] Error en bucle: {e}", flush=True)

            time.sleep(1)


def instalar(app):
    rec = Recordatorios(app)

    def _accion_poner(arg=None):
        res = rec.poner_recordatorio(arg)
        if hasattr(app, "cola") and app.cola:
            app.cola.put(("hablar", res))
        return res

    def _accion_listar(arg=None):
        res = rec.listar_recordatorios()
        if hasattr(app, "cola") and app.cola:
            app.cola.put(("hablar", res))
        return res

    def _accion_cancelar(arg=None):
        res = rec.cancelar_recordatorio(arg)
        if hasattr(app, "cola") and app.cola:
            app.cola.put(("hablar", res))
        return res

    acciones.registrar(
        "poner_recordatorio",
        _accion_poner,
        "pone un recordatorio para una hora o minutos (ej: en 20 minutos, mañana a las 8). Escribe: ACCION: poner_recordatorio | tiempo | texto",
        con_texto=True,
    )
    acciones.registrar(
        "listar_recordatorios",
        _accion_listar,
        "lista todos los recordatorios pendientes programados",
        con_texto=False,
    )
    acciones.registrar(
        "cancelar_recordatorio",
        _accion_cancelar,
        "cancela un recordatorio pendiente según su tema. Escribe: ACCION: cancelar_recordatorio | texto",
        con_texto=True,
    )
    # Alias retrocompatible
    acciones.registrar(
        "recordar",
        _accion_poner,
        "te avisa de algo en unos minutos o a una hora fija. Escribe: ACCION: recordar | minutos u hora | texto",
        con_texto=True,
    )
    return rec
