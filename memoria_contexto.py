"""Contexto dinámico y compacto de Memoria para los prompts de Kaya.

Sustituye la inyección estática de temas_abiertos_kaya.json. Usa hechos
verificados (SQLite), el ánimo actual y hasta dos bromas internas; registra en
estado.json los hechos ya inyectados para no repetir datos ni saludos al
despertar. El bloque completo se mantiene por debajo de 450 caracteres.
"""
import hashlib
import re
import threading
from datetime import datetime

import estado

_CLAVE = "memoria_contexto_sesion"
_MAX_CHARS = 360
_MAX_VISTOS = 24
_BROMA_MARCA = "[BROMA_INTERNA]"
_MAX_BROMAS = 2
_bloqueo = threading.RLock()


def _instancia():
    """Devuelve la instancia principal de Memoria, nunca crea una nueva."""
    try:
        import memoria
        return memoria.instancia_principal()
    except Exception:
        return None


def _limpio(texto, max_len=110):
    s = re.sub(r"^\[[^\]]+\]\s*", "", str(texto or "")).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:max_len].rstrip(" ,;.")


def hechos_verificados(memoria=None, limite=3):
    """Hechos explícitos, activos y con confianza alta; jamás inferencias."""
    mem = memoria if memoria is not None else _instancia()
    if mem is None:
        return []
    try:
        filas = mem.almacen.listar_recuerdos(300, usuario_id=mem.usuario_id)
    except Exception:
        return []
    salida = []
    for fila in filas:
        if fila.get("estado") != "activo" or fila.get("origen") != "explicito":
            continue
        try:
            confianza = float(fila.get("confianza") or 0)
        except (TypeError, ValueError):
            confianza = 0.0
        if confianza < 0.8:
            continue
        contenido = str(fila.get("contenido") or "")
        if _BROMA_MARCA in contenido:
            continue
        texto = _limpio(contenido)
        if len(texto) < 12:
            continue
        try:
            import memoria_filtro
            if memoria_filtro.es_ruido_extraccion(texto):
                continue
        except Exception:
            pass
        salida.append(texto)
        if len(salida) >= limite:
            break
    return salida


def resumen_conversaciones(memoria=None, limite=2):
    """Resumen breve de conversaciones previas: temáticos reales + diario."""
    mem = memoria if memoria is not None else _instancia()
    salida = []
    if mem is not None:
        try:
            temas = mem.datos.get("resumenes_tematicos") or {}
            for nombre, texto in list(temas.items())[-limite:]:
                res = _limpio(texto, 90)
                if res:
                    salida.append(f"{_limpio(nombre, 18)}: {res}"[:110])
        except Exception:
            pass
    try:
        import diario_helpers
        ultima = diario_helpers.leer_ultima()
        if ultima:
            salida.append(_limpio(ultima, 90))
    except Exception:
        pass
    return salida[:limite]


def bromas_internas(memoria=None, limite=_MAX_BROMAS):
    """Bromas, apodos o códigos propios vigentes, sin la etiqueta de almacenaje."""
    mem = memoria if memoria is not None else _instancia()
    if mem is None:
        return []
    try:
        filas = mem.almacen.listar_recuerdos(300, usuario_id=mem.usuario_id)
    except Exception:
        return []
    salida = []
    for fila in filas:
        if fila.get("estado") != "activo":
            continue
        contenido = str(fila.get("contenido") or "")
        if _BROMA_MARCA not in contenido:
            continue
        texto = contenido.split(_BROMA_MARCA, 1)[1]
        texto = re.sub(r"\s*\(contexto:[^)]*\)\s*$", "", texto).strip()
        texto = _limpio(texto, 90)
        if texto:
            salida.append(f"Broma: {texto}")
        if len(salida) >= limite:
            break
    return salida


def _directriz_emocional(memoria=None):
    """Ánimo real del mismo perfil; nunca inventa un tono."""
    try:
        import estado_emocional_kaya
        uid = getattr(memoria, "usuario_id", "local") if memoria is not None else "local"
        return estado_emocional_kaya.resumen_estado_emocional(uid)
    except Exception:
        return ""


def _hash(texto):
    return hashlib.sha1(texto.encode("utf-8", "replace")).hexdigest()[:12]


def _registro():
    try:
        datos = estado.cargar()
        reg = datos.get(_CLAVE)
        if not isinstance(reg, dict):
            reg = {}
        if not isinstance(reg.get("vistos"), list):
            reg["vistos"] = []
        return datos, reg
    except Exception:
        return {}, {"vistos": []}


def _asegurar_dia(reg):
    """Cuenta un despertar por día sin borrar lo ya mostrado."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    if reg.get("dia") != hoy:
        reg["dia"] = hoy
        reg["despertares"] = int(reg.get("despertares") or 0) + 1
    return reg


def registrar_despertar():
    """Registra explícitamente un despertar (mantiene el anti-repetición)."""
    with _bloqueo:
        datos, reg = _registro()
        _asegurar_dia(reg)
        reg["despertares"] = int(reg.get("despertares") or 0) + 1
        datos[_CLAVE] = reg
        estado.guardar(datos)
        return reg["despertares"]


def resetear_sesion():
    """Permite volver a inyectar datos (pruebas o cambio de perfil)."""
    with _bloqueo:
        datos, reg = _registro()
        reg["vistos"] = []
        datos[_CLAVE] = reg
        estado.guardar(datos)


def resumen_para_prompt(memoria=None, incluir_conversaciones=True):
    """Ánimo + bromas vigentes + solo datos aún no inyectados."""
    mem = memoria if memoria is not None else _instancia()
    hechos = hechos_verificados(mem)
    charlas = resumen_conversaciones(mem) if incluir_conversaciones else []
    obligatorios = []
    animo = _directriz_emocional(mem)
    if animo:
        obligatorios.append(animo[:160])
    obligatorios.extend(bromas_internas(mem))
    with _bloqueo:
        datos, reg = _registro()
        _asegurar_dia(reg)
        vistos = list(reg.get("vistos") or [])
        conocidos = set(vistos)
        candidatos = []
        for etiqueta, textos in (("hecho", hechos), ("charla", charlas)):
            for texto in textos:
                clave = _hash(etiqueta + ":" + texto)
                if clave in conocidos:
                    continue
                candidatos.append((etiqueta, texto, clave))
        bloques = list(obligatorios)
        aceptados = []
        for etiqueta, texto, clave in candidatos:
            prefijo = "Hecho" if etiqueta == "hecho" else "Charla"
            bloque = f"{prefijo}: {texto}"
            if len("; ".join(bloques + [bloque])) > _MAX_CHARS:
                break
            bloques.append(bloque)
            aceptados.append(clave)
        if not bloques:
            return ""
        vistos.extend(aceptados)
        reg["vistos"] = vistos[-_MAX_VISTOS:]
        datos[_CLAVE] = reg
        estado.guardar(datos)
    texto = "; ".join(bloques)[:_MAX_CHARS]
    return f"\n\n[Lo que ya sé de ti, sin repetirlo]: {texto}."


__all__ = [
    "hechos_verificados", "resumen_conversaciones", "bromas_internas",
    "registrar_despertar", "resetear_sesion", "resumen_para_prompt",
]
