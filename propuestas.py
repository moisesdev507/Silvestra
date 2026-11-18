"""Sistema autónomo de autopropuestas de mejora para Silvestra.

Detecta carencias reales, las guarda en propuestas.json, las presenta diariamente
o por voz, y cuando se aprueban redacta el prompt para Antigravity sin modificar código.
"""
import collections
import datetime
import difflib
import json
import os
import re
import threading
import time

import acciones
import estado
import ideas
import propuestas_prompt

RUTA_PROPUESTAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "propuestas.json")
RUTA_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "silvestra.log")

_instancia_gestor = None


def cargar_propuestas():
    if not os.path.exists(RUTA_PROPUESTAS):
        return []
    try:
        with open(RUTA_PROPUESTAS, "r", encoding="utf-8") as f:
            datos = json.load(f)
            return datos if isinstance(datos, list) else []
    except Exception:
        return []


def guardar_propuestas(datos):
    try:
        with open(RUTA_PROPUESTAS, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _es_similar(t1, t2, umbral=0.65):
    if not t1 or not t2:
        return False
    return difflib.SequenceMatcher(None, t1.lower().strip(), t2.lower().strip()).ratio() >= umbral


def notificar_idea_para_propuesta(texto):
    global _instancia_gestor
    if _instancia_gestor:
        _instancia_gestor.detectar_carencia_accion(texto)


class GestorPropuestas:
    def __init__(self, app):
        self.app = app
        self._bloqueo = threading.RLock()
        self.id_ultima_propuesta_presentada = estado.cargar().get("id_ultima_propuesta_presentada")
        self._detener = threading.Event()
        self._hilo = threading.Thread(target=self._bucle_segundo_plano, daemon=True, name="PropuestasMonitor")
        self._hilo.start()

    def _guardar_estado(self):
        datos = estado.cargar()
        datos["id_ultima_propuesta_presentada"] = self.id_ultima_propuesta_presentada
        estado.guardar(datos)

    def _generar_nuevo_id(self, propuestas):
        max_num = 0
        for p in propuestas:
            m = re.search(r"prop_(\d+)", p.get("id", ""))
            if m:
                max_num = max(max_num, int(m.group(1)))
        return f"prop_{max_num + 1}"

    def es_duplicada(self, descripcion, propuestas=None):
        props = propuestas if propuestas is not None else cargar_propuestas()
        for p in props:
            if _es_similar(p.get("descripcion", ""), descripcion):
                return True
        for item in ideas.cargar():
            if _es_similar(item.get("texto", ""), descripcion):
                return True
        return False

    def registrar_propuesta(self, descripcion, motivo, fuente="auto"):
        desc = (descripcion or "").strip()
        if len(desc) < 4:
            return None
        with self._bloqueo:
            props = cargar_propuestas()
            if len([p for p in props if p.get("estado") == "nueva"]) >= 10:
                print(f"[propuestas] Límite de 10 propuestas alcanzado: '{desc}'", flush=True)
                return None
            if self.es_duplicada(desc, props):
                print(f"[propuestas] Omitida por duplicado o rechazo: '{desc}'", flush=True)
                return None

            es_riesgoso, detalle = propuestas_prompt.evaluar_riesgo(desc, motivo)
            nuevo_id = self._generar_nuevo_id(props)
            nueva = {
                "id": nuevo_id,
                "fecha": time.strftime("%Y-%m-%d"),
                "descripcion": desc,
                "motivo": (motivo or "Detección automática").strip(),
                "fuente": fuente,
                "estado": "nueva",
                "riesgo": es_riesgoso,
                "detalle_riesgo": detalle,
            }
            props.append(nueva)
            guardar_propuestas(props)
            print(f"[propuestas] Guardada: {nuevo_id} - '{desc}' (fuente={fuente})", flush=True)
            return nueva

    def detectar_carencia_accion(self, texto):
        if not texto:
            return None
        return self.registrar_propuesta(f"Implementar habilidad: {texto.strip()}", "El usuario pidió una acción que no existe", fuente="accion_faltante")

    def detectar_desde_correccion(self, texto_usuario):
        if not texto_usuario:
            return None
        if re.search(r"\b(eso no|no era eso|así no|asi no|te equivocaste|no hagas eso|eso está mal|eso esta mal|no es lo que pedí|no es lo que pedi)\b", texto_usuario, re.I):
            ultimo = getattr(self.app, "ultimo_dicho", "")[:70]
            desc = f"Corregir comprensión tras corrección: '{texto_usuario.strip()}'"
            return self.registrar_propuesta(desc, f"El usuario corrigió la respuesta/acción anterior ('{ultimo}')", fuente="correccion_usuario")
        return None

    def detectar_errores_repetidos_log(self):
        if not os.path.exists(RUTA_LOG):
            return []
        conteo = collections.defaultdict(int)
        try:
            with open(RUTA_LOG, "rb") as f:
                f.seek(0, os.SEEK_END)
                tam = f.tell()
                leer_tam = min(tam, 32768)
                f.seek(max(0, tam - leer_tam))
                bloque = f.read().decode("utf-8", errors="ignore")
            for linea in bloque.splitlines():
                if any(k in linea for k in ["Error:", "Exception:", "[eventos] Error", "Traceback"]):
                    limpia = re.sub(r"\b0x[0-9a-fA-F]+\b", "", linea)
                    limpia = re.sub(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}", "", limpia)
                    limpia = re.sub(r'line \d+', 'line X', limpia).strip()
                    if len(limpia) > 15:
                        conteo[limpia[:90]] += 1
        except Exception:
            return []
        registradas = []
        for err, n in conteo.items():
            if n >= 3:
                p = self.registrar_propuesta(f"Reparar error de log: {err}", f"Apareció {n} veces repetidas en silvestra.log", fuente="error_repetido")
                if p:
                    registradas.append(p)
        return registradas

    def presentar_propuesta_diaria(self, forzar=False):
        telegram = getattr(self.app, "telegram", None)
        if not telegram or not getattr(telegram, "chat_id_autorizado", None):
            return False
        ahora = datetime.datetime.now()
        hoy = ahora.strftime("%Y-%m-%d")
        datos_est = estado.cargar()
        if not forzar:
            if ahora.hour >= 22 or ahora.hour < 7 or datos_est.get("ultima_propuesta_diaria_fecha") == hoy:
                return False

        with self._bloqueo:
            props = cargar_propuestas()
            abiertas = [p for p in props if p.get("estado") == "nueva"]
            if not abiertas:
                return False
            abiertas.sort(key=lambda p: 0 if p.get("fuente") in ("error_repetido", "correccion_usuario") else 1)
            elegida = abiertas[0]

            self.id_ultima_propuesta_presentada = elegida["id"]
            self._guardar_estado()
            datos_est["ultima_propuesta_diaria_fecha"] = hoy
            estado.guardar(datos_est)

            riesgo = f"\n⚠️ RIESGO: {elegida['detalle_riesgo']}" if elegida.get("riesgo") else ""
            msg = (
                f"💡 Propuesta de mejora ({elegida['id']}):\n"
                f"{elegida['descripcion']}\n\n"
                f"Motivo: {elegida['motivo']}{riesgo}\n\n"
                f"¿Quieres que te prepare el prompt? (Responde sí, no o después)"
            )
            telegram._enviar_telegram(telegram.chat_id_autorizado, msg)
            print(f"[propuestas] Presentada por Telegram: {elegida['id']}", flush=True)
            return True

    def ver_propuestas_voz(self):
        with self._bloqueo:
            abiertas = [p for p in cargar_propuestas() if p.get("estado") == "nueva"]
            if not abiertas:
                self.app.decir("No tengo ninguna propuesta de mejora pendiente por ahora.", 3500)
                return
            p = abiertas[0]
            self.id_ultima_propuesta_presentada = p["id"]
            self._guardar_estado()
            self.app.decir(f"Tengo esta propuesta: {p['descripcion']}. ¿Quieres que te prepare el prompt?", 5500)

    def aprobar_propuesta(self, id_prop=None):
        with self._bloqueo:
            props = cargar_propuestas()
            target = (id_prop or "").strip() or self.id_ultima_propuesta_presentada
            prop = next((p for p in props if (target and p.get("id") == target) or (not target and p.get("estado") == "nueva")), None)
            if not prop:
                self.app.decir("No encontré ninguna propuesta pendiente para aprobar.", 3500)
                return False, "No encontrada"

            prop["estado"] = "aprobada"
            guardar_propuestas(props)
            _, texto_prompt, _, _ = propuestas_prompt.redactar_prompt(self.app, prop)

            self.app.cola.put(("copiar_portapapeles", texto_prompt))
            self.app.cola.put(("hablar", "Ya lo copié, pégalo en Antigravity."))
            self.app.cola.put(("telegram_burbuja", f"[{prop['id']}] Ya lo copié al portapapeles."))

            telegram = getattr(self.app, "telegram", None)
            if telegram and getattr(telegram, "chat_id_autorizado", None):
                msg_tel = f"✅ Propuesta {prop['id']} aprobada. Ya lo copié al portapapeles de la laptop:\n\n{texto_prompt}"
                if len(msg_tel) > 4000:
                    telegram._enviar_telegram(telegram.chat_id_autorizado, f"✅ Propuesta {prop['id']} aprobada. Ya lo copié al portapapeles de la laptop. Aquí tienes el prompt:")
                    for i in range(0, len(texto_prompt), 3800):
                        telegram._enviar_telegram(telegram.chat_id_autorizado, texto_prompt[i:i+3800])
                else:
                    telegram._enviar_telegram(telegram.chat_id_autorizado, msg_tel)
            return True, f"Propuesta {prop['id']} aprobada."

    def rechazar_propuesta(self, id_prop=None):
        with self._bloqueo:
            props = cargar_propuestas()
            target = (id_prop or "").strip() or self.id_ultima_propuesta_presentada
            prop = next((p for p in props if (target and p.get("id") == target) or (not target and p.get("estado") == "nueva")), None)
            if not prop:
                return False, "No encontrada"
            prop["estado"] = "rechazada"
            guardar_propuestas(props)
            resp = f"Entendido, descarté la propuesta {prop['id']} y no volveré a proponerte lo mismo."
            self.app.cola.put(("hablar", "Entendido, no volveré a proponerte esto."))
            telegram = getattr(self.app, "telegram", None)
            if telegram and getattr(telegram, "chat_id_autorizado", None):
                telegram._enviar_telegram(telegram.chat_id_autorizado, resp)
            return True, resp

    def marcar_hecha(self, id_prop=None):
        with self._bloqueo:
            props = cargar_propuestas()
            target = (id_prop or "").strip() or self.id_ultima_propuesta_presentada
            prop = next((p for p in props if (target and p.get("id") == target) or (not target and p.get("estado") == "aprobada")), None)
            if not prop:
                return False, "No encontrada"
            prop["estado"] = "hecha"
            guardar_propuestas(props)
            resp = f"Propuesta {prop['id']} marcada como hecha."
            self.app.cola.put(("hablar", resp))
            return True, resp

    def atender_respuesta_telegram(self, chat_id, texto):
        if not self.id_ultima_propuesta_presentada:
            return False
        t = (texto or "").strip().lower()
        if re.match(r"^(s[ií]|dale|hazlo|prepara el prompt|prep[aá]ralo|apruebo|aprobar)$", t):
            self.aprobar_propuesta(self.id_ultima_propuesta_presentada)
            self.id_ultima_propuesta_presentada = None
            self._guardar_estado()
            return True
        if re.match(r"^(no|rechazar|descarta eso|desc[aá]rtalo|no me gusta)$", t):
            self.rechazar_propuesta(self.id_ultima_propuesta_presentada)
            self.id_ultima_propuesta_presentada = None
            self._guardar_estado()
            return True
        if re.match(r"^(despu[eé]s|luego|m[aá]s tarde|mas tarde|ahora no)$", t):
            telegram = getattr(self.app, "telegram", None)
            if telegram:
                telegram._enviar_telegram(chat_id, "Entendido, dejamos la propuesta pendiente para después.")
            self.id_ultima_propuesta_presentada = None
            self._guardar_estado()
            return True
        return False

    def _bucle_segundo_plano(self):
        time.sleep(10)
        while not self._detener.is_set():
            try:
                self.detectar_errores_repetidos_log()
                self.presentar_propuesta_diaria(forzar=False)
            except Exception as e:
                print(f"[propuestas] Error monitor: {e}", flush=True)
            for _ in range(300):
                if self._detener.is_set():
                    break
                time.sleep(2)


def instalar(app):
    global _instancia_gestor
    gestor = GestorPropuestas(app)
    _instancia_gestor = gestor

    acciones.registrar("proponer_mejora", lambda arg=None: gestor.registrar_propuesta(arg or "Mejora identificada", "Notado en conversación", fuente="proponer_mejora"), "propone una mejora o carencia que notas durante la conversación para preparar una actualización. Escribe: ACCION: proponer_mejora | descripción", con_texto=True)
    acciones.registrar("ver_propuestas", lambda: gestor.ver_propuestas_voz(), "revisa y dice en voz alta qué propuestas de mejora tiene pendientes para el sistema.")
    acciones.registrar("aprobar_propuesta", lambda arg=None: gestor.aprobar_propuesta(arg), "aprueba una propuesta de mejora para que Silvestra redacte el prompt para Antigravity. Escribe: ACCION: aprobar_propuesta | id_opcional", con_texto=True)
    acciones.registrar("rechazar_propuesta", lambda arg=None: gestor.rechazar_propuesta(arg), "rechaza una propuesta de mejora para descartarla y no volver a proponerla. Escribe: ACCION: rechazar_propuesta | id_opcional", con_texto=True)
    acciones.registrar("marcar_hecha", lambda arg=None: gestor.marcar_hecha(arg), "marca una propuesta de mejora como ya realizada. Escribe: ACCION: marcar_hecha | id_opcional", con_texto=True)
    acciones.registrar("forzar_propuesta", lambda arg=None: gestor.registrar_propuesta(arg or "Mejora de prueba", "Prueba manual solicitada", fuente="prueba_manual"), "crea una propuesta de mejora manualmente para pruebas. Escribe: ACCION: forzar_propuesta | descripción", con_texto=True)
    acciones.registrar("probar_propuesta_diaria", lambda: gestor.presentar_propuesta_diaria(forzar=True), "dispara el envío inmediato del mensaje de propuesta diaria a Telegram para pruebas.")
    return gestor
