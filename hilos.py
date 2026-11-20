"""Hilos abiertos y pendientes: temas que Silvestra quiere retomar en otra conversación."""
import datetime
import difflib
import json
import os
import re
import time

import acciones

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hilos.json")


def cargar():
    try:
        if os.path.exists(RUTA):
            with open(RUTA, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def guardar(datos):
    try:
        with open(RUTA, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def es_hilo_vencido(hilo, hoy=None):
    """Determina si un hilo pendiente ha caducado por antigüedad (>3 días) o fecha pasada."""
    if not hilo or not isinstance(hilo, dict):
        return True

    try:
        import memoria_tiempo as mt
        ref_hoy = mt.obtener_fecha_actual(hoy)
    except Exception:
        ref_hoy = datetime.date.today()

    texto = (hilo.get("texto") or "").strip()
    fecha_str = (hilo.get("fecha") or "").strip()

    # 1. Parsear fecha de creación del hilo
    fecha_creacion = None
    if fecha_str:
        try:
            parts = [int(p) for p in re.findall(r"\d+", fecha_str)]
            if len(parts) >= 3:
                if parts[0] > 1000:
                    fecha_creacion = datetime.date(parts[0], parts[1], parts[2])
                else:
                    fecha_creacion = datetime.date(parts[2], parts[1], parts[0])
        except Exception:
            pass

    # Si fue creado hace más de 3 días -> vencido
    if fecha_creacion:
        delta_creacion = (ref_hoy - fecha_creacion).days
        if delta_creacion > 3:
            return True

    # 2. Revisar si el texto contiene una fecha explícita (DD/MM/YYYY) o (YYYY-MM-DD)
    m_fecha = re.search(r"\(?(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})\)?", texto)
    if m_fecha:
        try:
            d_exp = datetime.date(int(m_fecha.group(3)), int(m_fecha.group(2)), int(m_fecha.group(1)))
            if d_exp < ref_hoy:
                return True
        except Exception:
            pass

    m_iso = re.search(r"\(?(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})\)?", texto)
    if m_iso:
        try:
            d_exp = datetime.date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
            if d_exp < ref_hoy:
                return True
        except Exception:
            pass

    # 3. Hilos creados en días anteriores o sin fecha que contienen menciones relativas caducas
    try:
        import memoria_tiempo as mt
        t_norm = mt.normalizar_texto(texto)
    except Exception:
        t_norm = texto.lower()

    tiene_relativo = bool(re.search(r"\b(ma[nñ]ana|hoy|esta\s+noche|esta\s+tarde|ayer)\b", t_norm))
    if tiene_relativo:
        if not fecha_creacion or fecha_creacion < ref_hoy:
            return True

    return False


def anotar_pendiente(texto):
    """Guarda un tema o hilo abierto pendiente con fechas relativas ancladas."""
    texto = (texto or "").strip()
    if not texto:
        return

    try:
        import memoria_tiempo as mt
        texto_anclado = mt.anclar_fechas_relativas(texto)
    except Exception:
        texto_anclado = texto

    fecha_hoy = time.strftime("%Y-%m-%d")
    datos = cargar()
    for d in datos:
        if difflib.SequenceMatcher(None, d.get("texto", "").lower(), texto_anclado.lower()).ratio() > 0.7:
            d["texto"] = texto_anclado
            d["estado"] = "abierto"
            d["fecha"] = fecha_hoy
            break
    else:
        datos.append({"texto": texto_anclado, "estado": "abierto", "fecha": fecha_hoy})
    guardar(datos)


def cerrar_pendiente(texto):
    """Marca como resuelto o cerrado un tema pendiente."""
    texto = (texto or "").strip().lower()
    if not texto:
        return
    datos = cargar()
    for d in datos:
        if d.get("estado", "abierto") == "abierto":
            d_txt = d.get("texto", "").lower()
            if texto in d_txt or d_txt in texto or difflib.SequenceMatcher(None, d_txt, texto).ratio() > 0.6:
                d["estado"] = "resuelto"
                d["fecha_cierre"] = time.strftime("%Y-%m-%d")
                break
    guardar(datos)


def limpiar_vencidos(hoy=None):
    """Marca como 'vencido' los hilos abiertos que hayan caducado."""
    datos = cargar()
    cambio = False
    for d in datos:
        if d.get("estado", "abierto") == "abierto" and es_hilo_vencido(d, hoy=hoy):
            d["estado"] = "vencido"
            cambio = True
    if cambio:
        guardar(datos)


def resumen(maximo=6):
    """Devuelve un texto con los hilos pendientes no vencidos para el prompt del cerebro."""
    datos = cargar()
    abiertos = []
    for d in datos:
        if d.get("estado", "abierto") == "abierto" and not es_hilo_vencido(d):
            abiertos.append(d)
        if len(abiertos) >= maximo:
            break

    if not abiertos:
        return "ninguno todavía"
    return "; ".join(d["texto"] for d in abiertos)


def instalar(app):
    acciones.registrar(
        "anotar_pendiente",
        anotar_pendiente,
        "anota un tema pendiente o hilo abierto para retomar en otra conversación. "
        "Escribe: ACCION: anotar_pendiente | tema pendiente a retomar",
        con_texto=True,
    )
    acciones.registrar(
        "cerrar_pendiente",
        cerrar_pendiente,
        "marca como resuelto o cerrado un tema pendiente del que ya hablaron. "
        "Escribe: ACCION: cerrar_pendiente | tema resuelto",
        con_texto=True,
    )
