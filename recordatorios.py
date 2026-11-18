"""Gestión persistente de recordatorios para Silvestra en recordatorios.json."""
import datetime
import json
import os
import re
import threading
import time

import acciones

RUTA_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordatorios.json")


def _cargar():
    if not os.path.exists(RUTA_JSON):
        return []
    try:
        with open(RUTA_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _guardar(datos):
    try:
        with open(RUTA_JSON, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[recordatorios] Error guardando JSON: {e}", flush=True)


def parsear_tiempo(arg):
    """Interpreta minutos u hora exacta ('10 | texto', 'a las 5:30 | texto', 'en 1 hora | texto')."""
    if not arg:
        return None, None, None
    partes = arg.split("|", 1)
    tiempo_str = partes[0].strip().lower()
    texto = partes[1].strip() if len(partes) > 1 else "lo que me pediste"
    ahora = datetime.datetime.now()

    # 1. En X minutos (ej: '10', 'en 15 minutos', '15 min')
    m_min = re.search(r"(\d+)\s*(?:minutos?|mins?|$)", tiempo_str)
    if m_min and ("a las" not in tiempo_str and ":" not in tiempo_str):
        mins = int(m_min.group(1))
        if mins > 0:
            target = ahora + datetime.timedelta(minutes=mins)
            return target.timestamp(), target.strftime("%H:%M"), texto

    # 2. En X horas (ej: 'en 2 horas')
    m_horas = re.search(r"en\s+(\d+)\s+horas?", tiempo_str)
    if m_horas:
        horas = int(m_horas.group(1))
        if horas > 0:
            target = ahora + datetime.timedelta(hours=horas)
            return target.timestamp(), target.strftime("%H:%M"), texto

    # 3. A las H:M o H am/pm (ej: 'a las 5:30', 'a las 5 pm', '17:00', '5:00 pm')
    m_hora = re.search(r"(?:a\s+las\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", tiempo_str)
    if m_hora:
        h = int(m_hora.group(1))
        m = int(m_hora.group(2) or 0)
        meridiano = m_hora.group(3)
        if meridiano == "pm" and h < 12:
            h += 12
        elif meridiano == "am" and h == 12:
            h = 0
        if 0 <= h <= 23 and 0 <= m <= 59:
            target = ahora.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= ahora:
                target += datetime.timedelta(days=1)
            return target.timestamp(), target.strftime("%H:%M"), texto

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
        creador = getattr(self.app.memoria, "creador", "Moisés") or "Moisés"
        ahora_ts = time.time()
        with self._bloqueo:
            datos = _cargar()
            pendientes = []
            vencidos = []
            for r in datos:
                if not r.get("completado"):
                    if r.get("timestamp", 0) < ahora_ts:
                        r["completado"] = True
                        vencidos.append(r)
                    else:
                        pendientes.append(r)
            if vencidos:
                _guardar(datos)
                for v in vencidos:
                    msg = f"{creador}, mientras no estaba se te pasó este recordatorio: {v['texto']}."
                    print(f"[recordatorios] Vencido al arrancar: {v['texto']}", flush=True)
                    self.app.cola.put(("hablar", msg))

    def agregar(self, arg):
        """Agrega un recordatorio y devuelve mensaje de confirmación."""
        ts, hora_str, texto = parsear_tiempo(arg)
        if not ts:
            return "No te entendí la hora o los minutos para el recordatorio. Dímelo de nuevo."

        creador = getattr(self.app.memoria, "creador", "Moisés") or "Moisés"
        item = {
            "id": int(time.time() * 1000),
            "texto": texto,
            "timestamp": ts,
            "hora_exacta": hora_str,
            "fecha": datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
            "completado": False,
        }
        with self._bloqueo:
            datos = _cargar()
            datos.append(item)
            _guardar(datos)

        print(f"[recordatorios] Agregado: '{texto}' a las {hora_str}", flush=True)
        return f"Listo, {creador}. Te recordaré {texto} a las {hora_str}."

    def _bucle(self):
        while not self._detener.is_set():
            try:
                ahora_ts = time.time()
                creador = getattr(self.app.memoria, "creador", "Moisés") or "Moisés"
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
                    print(f"[recordatorios] Disparado: {txt}", flush=True)
                    self.app.cola.put(("hablar", aviso))
                    puente = getattr(self.app, "telegram", None)
                    if puente and getattr(puente, "chat_id_autorizado", None):
                        puente.avisar_celular(f"🔔 Recordatorio: {txt}", forzar=True)

            except Exception as e:
                print(f"[recordatorios] Error en bucle: {e}", flush=True)

            time.sleep(5)


def instalar(app):
    rec = Recordatorios(app)
    acciones.registrar(
        "recordar",
        lambda arg=None: app.cola.put(("hablar", rec.agregar(arg))),
        "te avisa de algo en unos minutos o a una hora fija. Escribe: ACCION: recordar | minutos u hora | qué recordar",
        con_texto=True,
    )
    return rec
