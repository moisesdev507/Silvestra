"""Gestión de datos del panel de información y reloj de mesa para la tablet."""
import datetime
import json
import os
import threading
import time

import estado

RUTA_RECORDATORIOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordatorios.json")


def log(mensaje):
    """Imprime mensajes con el prefijo estandarizado [pantalla_remota]."""
    print(f"[pantalla_remota] {mensaje}", flush=True)


class GestorPanelRemoto:
    """Recolecta clima, próximos recordatorios, saludo matutino y hora sin consultas de red extras."""

    def __init__(self, app):
        self.app = app
        self._lock = threading.RLock()
        self._detener = threading.Event()
        self.cache_panel = {
            "clima": "",
            "recordatorios": [],
            "saludo": "",
            "modo_privado": False,
            "es_noche": False,
            "hora_12": "",
            "ampm": "",
            "fecha": "",
            "ts": 0,
        }
        self.actualizar_cache()
        self._hilo = threading.Thread(target=self._bucle_actualizacion, daemon=True, name="PanelRemotoLoop")
        self._hilo.start()

    def _bucle_actualizacion(self):
        """Actualiza los datos del panel cada 15 segundos en segundo plano."""
        while not self._detener.is_set():
            try:
                self.actualizar_cache()
            except Exception as e:
                log(f"Error actualizando panel remoto: {e}")
            for _ in range(15):
                if self._detener.is_set():
                    break
                time.sleep(1)

    def actualizar_cache(self):
        """Obtiene de memoria y disco los datos del panel con manejo tolerante a fallos."""
        with self._lock:
            ahora = datetime.datetime.now()

            # 1. Hora 12h y fecha en español (hora local de Panamá)
            h_int = ahora.hour % 12
            if h_int == 0:
                h_int = 12
            hora_12 = f"{h_int}:{ahora.strftime('%M')}"
            ampm = "AM" if ahora.hour < 12 else "PM"

            dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
            fecha = f"{dias[ahora.weekday()]}, {ahora.day} de {meses[ahora.month - 1]}"

            # 2. Modo noche (entre las 10 PM y las 6 AM)
            es_noche = (ahora.hour >= 22 or ahora.hour < 6)

            # 3. Estado persistente (modo privado y último saludo)
            est = estado.cargar()
            modo_privado = bool(est.get("tablet_modo_privado", False))
            ultimo_saludo = est.get("ultimo_saludo", "")
            saludo_corto = ""
            if ultimo_saludo:
                saludo_corto = str(ultimo_saludo).strip().replace("\n", " ")
                if len(saludo_corto) > 110:
                    saludo_corto = saludo_corto[:107] + "..."

            # 4. Clima (reutilizado desde hud.py sin consultas de red)
            clima_txt = ""
            if hasattr(self.app, "ultimo_clima") and self.app.ultimo_clima:
                clima_txt = str(self.app.ultimo_clima).strip()
            elif hasattr(self.app, "hud") and self.app.hud and hasattr(self.app.hud, "lbl_clima"):
                try:
                    clima_txt = self.app.hud.lbl_clima.text().strip()
                except Exception:
                    pass

            # 5. Próximos recordatorios (máx 3 con hora y título corto)
            recs_lista = []
            if not modo_privado and os.path.exists(RUTA_RECORDATORIOS):
                try:
                    with open(RUTA_RECORDATORIOS, "r", encoding="utf-8") as f:
                        todos = json.load(f)
                    ahora_ts = time.time()
                    pendientes = [
                        r for r in todos
                        if not r.get("completado") and r.get("timestamp", 0) >= ahora_ts - 300
                    ]
                    pendientes.sort(key=lambda x: x.get("timestamp", 0))
                    for r in pendientes[:3]:
                        txt = r.get("texto", "Recordatorio").strip()
                        if len(txt) > 34:
                            txt = txt[:31] + "..."
                        recs_lista.append({
                            "hora": r.get("hora_exacta", "--:--"),
                            "texto": txt,
                        })
                except Exception:
                    recs_lista = []

            self.cache_panel = {
                "clima": clima_txt,
                "recordatorios": recs_lista,
                "saludo": saludo_corto,
                "modo_privado": modo_privado,
                "es_noche": es_noche,
                "hora_12": hora_12,
                "ampm": ampm,
                "fecha": fecha,
                "ts": ahora.timestamp(),
            }

    def obtener_datos(self):
        """Retorna una copia de los datos del panel en caché."""
        with self._lock:
            return dict(self.cache_panel)

    def fijar_modo_privado(self, privado):
        """Guarda y actualiza el modo privado de la tablet."""
        with self._lock:
            est = estado.cargar()
            est["tablet_modo_privado"] = bool(privado)
            estado.guardar(est)
            self.cache_panel["modo_privado"] = bool(privado)
            if privado:
                self.cache_panel["recordatorios"] = []
            log(f"Modo privado {'activado' if privado else 'desactivado'}.")
            return bool(privado)
