"""Persistencia y datos para el perfil de conversación y registro de charlas."""
import datetime
import json
import os
import re
import threading
import time

BASE = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_CONVERSACIONES = os.path.join(BASE, "conversaciones_dia.json")
ARCHIVO_PERFIL = os.path.join(BASE, "perfil_conversacion.json")

_lock = threading.RLock()

PALABRAS_PRIVADAS = (
    "clave", "password", "contraseñ", "contrasena", "token", "api_key",
    "apikey", "secret", "gsk_", "sk-", "pin de acceso", "credencial", "tarjeta", "cvv",
)

PERFIL_POR_DEFECTO = {
    "estilo": {
        "palabras_y_apodos": [],
        "muletillas": [],
        "formalidad": "informal y cercana",
        "largo_tipico": "frases cortas y directas",
    },
    "costumbres_y_horarios": [],
    "hilos_abiertos": [],
    "bromas_y_referencias": [],
    "ultima_reflexion": None,
}


def log(mensaje):
    """Imprime mensajes con el prefijo estandarizado [aprendizaje]."""
    print(f"[aprendizaje] {mensaje}", flush=True)


def contiene_datos_sensibles(texto):
    """True si el texto contiene términos asociados a claves o credenciales."""
    if not texto:
        return False
    t = str(texto).lower()
    return any(p in t for p in PALABRAS_PRIVADAS)


def es_buen_momento():
    """True si no estamos en horas silenciosas o madrugada (7:00 a 22:00)."""
    h = datetime.datetime.now().hour
    return 7 <= h < 22


def cargar_conversaciones():
    """Carga conversaciones_dia.json podando días que superen los 7 días."""
    with _lock:
        if not os.path.exists(ARCHIVO_CONVERSACIONES):
            return {}
        try:
            with open(ARCHIVO_CONVERSACIONES, "r", encoding="utf-8") as f:
                datos = json.load(f)
                if not isinstance(datos, dict):
                    return {}
            limite = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
            return {k: v for k, v in datos.items() if k >= limite}
        except Exception as e:
            log(f"Error leyendo {ARCHIVO_CONVERSACIONES}: {e}")
            return {}


def guardar_conversaciones(datos):
    """Guarda conversaciones_dia.json manteniendo solo los últimos 7 días."""
    with _lock:
        try:
            limite = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
            podado = {k: v for k, v in datos.items() if k >= limite}
            with open(ARCHIVO_CONVERSACIONES, "w", encoding="utf-8") as f:
                json.dump(podado, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            log(f"Error guardando {ARCHIVO_CONVERSACIONES}: {e}")
            return False


_perfil_cache = None
_perfil_mtime = 0.0
_perfil_ts = 0.0


def cargar_perfil():
    """Carga perfil_conversacion.json con caché en RAM de baja latencia (<1ms)."""
    global _perfil_cache, _perfil_mtime, _perfil_ts
    ahora = time.time()
    with _lock:
        if not os.path.exists(ARCHIVO_PERFIL):
            return json.loads(json.dumps(PERFIL_POR_DEFECTO))
        try:
            mtime = os.path.getmtime(ARCHIVO_PERFIL)
            if _perfil_cache is not None and mtime == _perfil_mtime and (ahora - _perfil_ts < 5.0):
                return json.loads(json.dumps(_perfil_cache))
            with open(ARCHIVO_PERFIL, "r", encoding="utf-8") as f:
                datos = json.load(f)
                if isinstance(datos, dict):
                    res = json.loads(json.dumps(PERFIL_POR_DEFECTO))
                    res.update(datos)
                    if not isinstance(res.get("estilo"), dict):
                        res["estilo"] = dict(PERFIL_POR_DEFECTO["estilo"])
                    _perfil_cache = res
                    _perfil_mtime = mtime
                    _perfil_ts = ahora
                    return json.loads(json.dumps(res))
        except Exception as e:
            log(f"Error leyendo {ARCHIVO_PERFIL}: {e}")
        return json.loads(json.dumps(PERFIL_POR_DEFECTO))


def guardar_perfil(datos):
    """Guarda perfil_conversacion.json de forma segura actualizando la caché en RAM."""
    global _perfil_cache, _perfil_mtime, _perfil_ts
    with _lock:
        try:
            with open(ARCHIVO_PERFIL, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=2)
            _perfil_cache = json.loads(json.dumps(datos))
            _perfil_mtime = os.path.getmtime(ARCHIVO_PERFIL) if os.path.exists(ARCHIVO_PERFIL) else time.time()
            _perfil_ts = time.time()
            return True
        except Exception as e:
            log(f"Error guardando {ARCHIVO_PERFIL}: {e}")
            return False


def registrar_interaccion(usuario, respuesta, emocion="neutral"):
    """Registra un turno de conversación y cierra hilos pendientes al contestar Moisés."""
    if not usuario or not respuesta:
        return

    if contiene_datos_sensibles(usuario) or contiene_datos_sensibles(respuesta):
        log("Conversación descartada del registro por contener términos sensibles.")
        return

    with _lock:
        hoy_str = datetime.date.today().strftime("%Y-%m-%d")
        hora_str = datetime.datetime.now().strftime("%H:%M:%S")

        perfil = cargar_perfil()
        hilos = perfil.get("hilos_abiertos", [])
        cambio_hilos = False
        for h in hilos:
            if h.get("esperando_respuesta") and not h.get("cerrado"):
                h["cerrado"] = True
                h["esperando_respuesta"] = False
                cambio_hilos = True
                log(f"Hilo cerrado tras respuesta del usuario: «{h.get('tema')}»")

        if cambio_hilos:
            guardar_perfil(perfil)

        datos = cargar_conversaciones()
        lista_dia = datos.setdefault(hoy_str, [])
        lista_dia.append({
            "hora": hora_str,
            "usuario": str(usuario).strip()[:400],
            "respuesta": str(respuesta).strip()[:400],
            "emocion": str(emocion).strip(),
        })
        guardar_conversaciones(datos)


def extraer_json_robusto(texto):
    """Parsea el bloque JSON retornado por el modelo LLM."""
    if not texto:
        return None
    limpio = re.sub(r"^```(?:json)?\s*", "", texto.strip(), flags=re.I)
    limpio = re.sub(r"\s*```$", "", limpio.strip())
    try:
        return json.loads(limpio)
    except Exception:
        m = re.search(r"\{.*\}", limpio, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return None


def resumen_para_prompt(texto_actual=None):
    """Genera un resumen corto del perfil (<= ~600 caracteres) para el prompt del cerebro."""
    with _lock:
        perfil = cargar_perfil()
        estilo = perfil.get("estilo", {})
        palabras = estilo.get("palabras_y_apodos", [])
        muletillas = estilo.get("muletillas", [])
        costumbres = perfil.get("costumbres_y_horarios", [])
        bromas = perfil.get("bromas_y_referencias", [])
        hilos = perfil.get("hilos_abiertos", [])

        if not any([palabras, muletillas, costumbres, bromas, hilos]):
            return ""

        hoy_str = datetime.date.today().strftime("%Y-%m-%d")
        hilo_preguntar = None
        if es_buen_momento():
            for h in hilos:
                if not h.get("cerrado") and not h.get("preguntado"):
                    fecha = h.get("fecha")
                    if fecha and fecha <= hoy_str:
                        hilo_preguntar = h
                        h["preguntado"] = True
                        h["esperando_respuesta"] = True
                        guardar_perfil(perfil)
                        break

        detalles = []
        form = estilo.get("formalidad")
        largo = estilo.get("largo_tipico")
        if form or largo:
            detalles.append(f"Tono {form or 'cercano'}, {largo or 'frases directas'}")
        if palabras:
            detalles.append(f"Vocabulario: {', '.join(palabras[:3])}")
        if muletillas:
            detalles.append(f"Muletillas: {', '.join(muletillas[:2])}")
        if costumbres:
            detalles.append(f"Costumbres: {'; '.join(costumbres[:2])}")
        if bromas:
            detalles.append(f"Referencias: {'; '.join(bromas[:2])}")

        hilos_activos = [h for h in hilos if not h.get("cerrado")]
        if hilo_preguntar:
            detalles.append(f"Tema cumplido para preguntar hoy cómo le fue: «{hilo_preguntar.get('tema')}»")
        elif hilos_activos:
            primero = hilos_activos[0]
            f_str = f" ({primero.get('fecha')})" if primero.get("fecha") else ""
            detalles.append(f"Tema abierto: «{primero.get('tema')}»{f_str}")

        linea_datos = "; ".join(detalles)
        guia = (
            "Perfil conversacional de Moisés (refleja su estilo con naturalidad sin burlarte):\n"
            f"- {linea_datos}.\n"
            "Regla: retoma máximo UN tema si viene al caso con delicadeza, sin interrogar."
        )

        if len(guia) > 600:
            guia = guia[:596] + "..."
        return guia


def eliminar_del_perfil(clave):
    """Borra un elemento coincidente de estilo, costumbres, hilos o bromas."""
    with _lock:
        perfil = cargar_perfil()
        c = clave.strip().lower()
        estilo = perfil.get("estilo", {})
        p0, m0 = len(estilo.get("palabras_y_apodos", [])), len(estilo.get("muletillas", []))
        c0, b0 = len(perfil.get("costumbres_y_horarios", [])), len(perfil.get("bromas_y_referencias", []))
        h0 = len(perfil.get("hilos_abiertos", []))

        estilo["palabras_y_apodos"] = [p for p in estilo.get("palabras_y_apodos", []) if c not in p.lower()]
        estilo["muletillas"] = [m for m in estilo.get("muletillas", []) if c not in m.lower()]
        perfil["costumbres_y_horarios"] = [x for x in perfil.get("costumbres_y_horarios", []) if c not in x.lower()]
        perfil["bromas_y_referencias"] = [x for x in perfil.get("bromas_y_referencias", []) if c not in x.lower()]
        perfil["hilos_abiertos"] = [h for h in perfil.get("hilos_abiertos", []) if c not in h.get("tema", "").lower() and str(h.get("id")) != c]

        borrado = any([
            len(estilo["palabras_y_apodos"]) < p0, len(estilo["muletillas"]) < m0,
            len(perfil["costumbres_y_horarios"]) < c0, len(perfil["bromas_y_referencias"]) < b0,
            len(perfil["hilos_abiertos"]) < h0,
        ])
        if borrado:
            guardar_perfil(perfil)
        return borrado


def reiniciar_perfil_y_conversaciones():
    """Restablece los datos a su estado vacío inicial."""
    with _lock:
        guardar_perfil(json.loads(json.dumps(PERFIL_POR_DEFECTO)))
        guardar_conversaciones({})


def actualizar_perfil_con_analisis(nuevo, hoy_str):
    """Actualiza perfil_conversacion.json a partir del dict devuelto por el LLM.
    
    Devuelve (perfil_actualizado, lista_campos_modificados).
    """
    with _lock:
        perfil = cargar_perfil()
        campos = []

        # Actualizar estilo
        n_estilo = nuevo.get("estilo", {})
        if isinstance(n_estilo, dict):
            estilo_mod = False
            pal_nuevas = [str(p).strip() for p in n_estilo.get("palabras_y_apodos", []) if p]
            pal_prev = list(perfil["estilo"].get("palabras_y_apodos", []))
            pal_comb = list(dict.fromkeys(pal_prev + pal_nuevas))[-10:]
            if pal_comb != pal_prev:
                perfil["estilo"]["palabras_y_apodos"] = pal_comb
                estilo_mod = True

            mul_nuevas = [str(m).strip() for m in n_estilo.get("muletillas", []) if m]
            mul_prev = list(perfil["estilo"].get("muletillas", []))
            mul_comb = list(dict.fromkeys(mul_prev + mul_nuevas))[-6:]
            if mul_comb != mul_prev:
                perfil["estilo"]["muletillas"] = mul_comb
                estilo_mod = True

            if n_estilo.get("formalidad"):
                f = str(n_estilo["formalidad"]).strip()[:80]
                if f and f != perfil["estilo"].get("formalidad"):
                    perfil["estilo"]["formalidad"] = f
                    estilo_mod = True

            if n_estilo.get("largo_tipico"):
                l = str(n_estilo["largo_tipico"]).strip()[:80]
                if l and l != perfil["estilo"].get("largo_tipico"):
                    perfil["estilo"]["largo_tipico"] = l
                    estilo_mod = True

            if estilo_mod:
                campos.append("estilo")

        # Actualizar costumbres
        n_cost = nuevo.get("costumbres_y_horarios", [])
        if isinstance(n_cost, list):
            cost_prev = list(perfil.get("costumbres_y_horarios", []))
            cost_nuevas = [str(c).strip() for c in n_cost if c]
            cost_comb = list(dict.fromkeys(cost_prev + cost_nuevas))[-8:]
            if cost_comb != cost_prev:
                perfil["costumbres_y_horarios"] = cost_comb
                campos.append("costumbres")

        # Actualizar bromas y referencias
        n_brom = nuevo.get("bromas_y_referencias", [])
        if isinstance(n_brom, list):
            brom_prev = list(perfil.get("bromas_y_referencias", []))
            brom_nuevas = [str(b).strip() for b in n_brom if b]
            brom_comb = list(dict.fromkeys(brom_prev + brom_nuevas))[-8:]
            if brom_comb != brom_prev:
                perfil["bromas_y_referencias"] = brom_comb
                campos.append("bromas")

        # Actualizar hilos abiertos preservando estados anteriores
        n_hilos = nuevo.get("hilos_abiertos", [])
        if isinstance(n_hilos, list):
            hilos_previos = list(perfil.get("hilos_abiertos", []))
            temas_existentes = {h.get("tema", "").lower(): h for h in hilos_previos}
            siguiente_id = max([h.get("id", 0) for h in hilos_previos] or [0]) + 1
            hilos_mod = False

            for nh in n_hilos:
                if not isinstance(nh, dict):
                    continue
                tema = str(nh.get("tema", "")).strip()
                if not tema:
                    continue
                if tema.lower() in temas_existentes:
                    previo = temas_existentes[tema.lower()]
                    fec = nh.get("fecha", "")
                    if fec and fec != previo.get("fecha"):
                        previo["fecha"] = fec
                        hilos_mod = True
                else:
                    hilos_previos.append({
                        "id": siguiente_id,
                        "tema": tema,
                        "fecha": nh.get("fecha", ""),
                        "preguntado": False,
                        "cerrado": False,
                        "esperando_respuesta": False,
                    })
                    siguiente_id += 1
                    hilos_mod = True

            perfil["hilos_abiertos"] = hilos_previos[-10:]
            if hilos_mod:
                campos.append("hilos_abiertos")

        perfil["ultima_reflexion"] = hoy_str
        guardar_perfil(perfil)
        return perfil, campos
