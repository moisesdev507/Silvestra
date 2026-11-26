"""Contexto dinámico y compacto de Memoria para los prompts de Kaya.

Sustituye la inyección estática de temas_abiertos_kaya.json. Usa hechos
verificados (SQLite), el ánimo actual, hasta dos bromas, un recuerdo semántico
y un seguimiento vigente. El anti-repetición vive en RAM y solo se persiste en
estado.json al registrar turnos o despertares. Bloque total <= 480 caracteres.
"""
import hashlib
import re
import threading
from collections import deque
from datetime import datetime

import estado
import memoria_ficha
import memoria_unificada

_CLAVE = "memoria_contexto_sesion"
_MAX_CHARS = 430
_MAX_VISTOS = 24
_BROMA_MARCA = "[BROMA_INTERNA]"
_MAX_BROMAS = 2
_TURNOS = deque(maxlen=16)
_bloqueo = threading.RLock()
_espejo = None
# Ledger de anti-repetición: se lee del disco solo en rutas de escritura.
_LEDGER = {"vistos": [], "dia": None, "despertares": 0}
_LEDGER_HIDRATADO = False
_VISTOS_PENDIENTES = False


def _instancia():
    """Devuelve la instancia principal de Memoria, nunca crea una nueva."""
    try:
        import memoria
        return memoria.instancia_principal()
    except Exception:
        return None


def usuario_id_canonical():
    """Id único compartido por Live y Celeste."""
    return memoria_unificada.usuario_id_canonical()


def _limpio(texto, max_len=110):
    s = re.sub(r"^\[[^\]]+\]\s*", "", str(texto or "")).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:max_len].rstrip(" ,;.")


_PREGUNTA_KAYA = re.compile(
    r"^(?:cómo|que|qué|cuál|cuáles|quién|quiénes|dónde|cuándo|por qué|para qué|"
    r"hay (?:algún|alguna|algo)|puedes|podrías|te gustaría|necesitas|dime|"
    r"cuéntame|explícame|averigua)\b",
    re.IGNORECASE,
)


def es_pregunta_kaya(texto):
    """True si el texto es una pregunta o pedido del asistente, no un hecho."""
    limpio = _limpio(texto, 400).strip()
    if not limpio or limpio.endswith("?") or limpio.startswith("¿"):
        return True
    return bool(_PREGUNTA_KAYA.match(limpio.casefold()))


def hechos_verificados(memoria=None, limite=3):
    """Hechos activos y verificados (explícitos o migrados), sin preguntas de Kaya."""
    mem = memoria if memoria is not None else _instancia()
    if mem is None:
        return []
    try:
        filas = mem.almacen.listar_recuerdos(300, usuario_id=mem.usuario_id)
    except Exception:
        return []
    salida = []
    for fila in filas:
        if (fila.get("estado") != "activo"
                or fila.get("origen") not in ("explicito", "migrado")):
            continue
        try:
            confianza = float(fila.get("confianza") or 0)
        except (TypeError, ValueError):
            confianza = 0.0
        if confianza < 0.8:
            continue
        contenido = str(fila.get("contenido") or "")
        if _BROMA_MARCA in contenido or es_pregunta_kaya(contenido):
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


def instalar_espejo(fn=None):
    """Enlaza cerebro.historial como reflejo de los turnos reales compartidos."""
    global _espejo
    with _bloqueo:
        _espejo = fn if callable(fn) else None


def registrar_turno(rol, texto, espejo=True):
    """Acumula turnos reales de la sesión y los refleja en cerebro.historial."""
    limpio = _limpio(texto, 1400)
    if not limpio:
        return
    papel = "user" if str(rol or "").lower() in ("user", "usuario", "tú") else "kaya"
    with _bloqueo:
        _TURNOS.append({"role": papel, "content": limpio})
        destino = _espejo if espejo else None
    _hidratar_ledger()
    _volcar_si_pendiente()
    if destino is not None:
        try:
            destino(papel, limpio)
        except Exception:
            pass


def registrar_par(texto_usuario, texto_kaya):
    """Registra el par usuario/Kaya de Celeste y aprende del turno real."""
    registrar_turno("user", texto_usuario, espejo=False)
    registrar_turno("kaya", texto_kaya, espejo=False)
    if str(texto_usuario or "").strip():
        memoria_unificada.aprender_del_turno_async(texto_usuario, canal="texto")


def historial_conversacion_activa(max_turnos=12, max_chars=1400):
    """Últimos turnos reales compartidos por Live y Celeste, con roles de chat."""
    n = max(1, min(24, int(max_turnos)))
    limite = max(1, int(max_chars))
    with _bloqueo:
        recientes = list(_TURNOS)[-n:]
    salida, usados = [], 0
    for turno in reversed(recientes):
        contenido = str(turno.get("content") or "").strip()
        if not contenido:
            continue
        restante = limite - usados
        if restante <= 0:
            break
        if len(contenido) > restante:
            contenido = contenido[:restante].rstrip()
        papel = "user" if turno.get("role") == "user" else "assistant"
        salida.append({"role": papel, "content": contenido})
        usados += len(contenido)
    salida.reverse()
    return salida


def turnos_recientes():
    """Copia de los turnos recientes para el extractor y el ciclo de sueño."""
    with _bloqueo:
        return list(_TURNOS)


def _consulta_actual():
    with _bloqueo:
        for turno in reversed(_TURNOS):
            if turno["role"] == "user":
                return turno["content"]
    return ""


def semanticos_relevantes(memoria=None, consulta=None, limite=1):
    """Recuerdos por significado del último tema real, sin repetir hechos."""
    q = _limpio(consulta if consulta is not None else _consulta_actual(), 120)
    if not q:
        return []
    mem = memoria if memoria is not None else _instancia()
    uid = usuario_id_canonical()
    try:
        import memoria_semantica
        filas = memoria_semantica.buscar_semantico_kaya(q, usuario_id=uid, limite=limite)
    except Exception:
        return []
    conocidos = {_limpio(x).casefold()[:40]
                 for x in (hechos_verificados(mem) + resumen_conversaciones(mem))}
    salida = []
    for _id, texto, _score in filas:
        limpio = _limpio(texto, 80)
        clave = limpio.casefold()[:40]
        if len(limpio) < 8 or clave in conocidos:
            continue
        conocidos.add(clave)
        salida.append(f"Recuerdo: {limpio}")
        if len(salida) >= limite:
            break
    return salida


def _directriz_emocional(memoria=None):
    """Ánimo real del mismo perfil; nunca inventa un tono."""
    try:
        import estado_emocional_kaya
        uid = usuario_id_canonical()
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


def _ledger_ram():
    """Copia del ledger en RAM: ninguna lectura de prompt toca estado.json."""
    with _bloqueo:
        return dict(_LEDGER)


def _hidratar_ledger():
    """Carga el ledger desde estado.json solo al registrar turnos/despertares."""
    global _LEDGER_HIDRATADO
    with _bloqueo:
        if _LEDGER_HIDRATADO:
            return
        _datos, reg = _registro()
        _LEDGER["vistos"] = list(reg.get("vistos") or [])
        _LEDGER["dia"] = reg.get("dia")
        _LEDGER["despertares"] = int(reg.get("despertares") or 0)
        _LEDGER_HIDRATADO = True


def _persistir_ledger():
    """Escribe el ledger ya acumulado en RAM (único punto de I/O del anti-repetición)."""
    global _VISTOS_PENDIENTES
    with _bloqueo:
        datos, reg = _registro()
        reg.update(_ledger_ram())
        reg["vistos"] = list(_LEDGER["vistos"])
        datos[_CLAVE] = reg
        estado.guardar(datos)
        _VISTOS_PENDIENTES = False


def _volcar_si_pendiente():
    """Difiere la escritura de los vistos hasta el siguiente turno real."""
    if _VISTOS_PENDIENTES:
        _persistir_ledger()


def _asegurar_dia(reg):
    """Cuenta un despertar por día sin borrar lo ya mostrado."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    if reg.get("dia") != hoy:
        reg["dia"] = hoy
        reg["despertares"] = int(reg.get("despertares") or 0) + 1
    return reg


def registrar_despertar():
    """Registra explícitamente un despertar (mantiene el anti-repetición)."""
    _hidratar_ledger()
    with _bloqueo:
        _asegurar_dia(_LEDGER)
        _LEDGER["despertares"] = int(_LEDGER["despertares"] or 0) + 1
        _persistir_ledger()
        return int(_LEDGER["despertares"])


def resetear_sesion():
    """Permite volver a inyectar datos (pruebas o cambio de perfil)."""
    _hidratar_ledger()
    with _bloqueo:
        _LEDGER["vistos"] = []
        _persistir_ledger()


def resumen_estable(memoria=None, max_chars=430):
    """Ficha y recuerdos sin anti-repetición: iguales en cada reconexión."""
    mem = memoria if memoria is not None else _instancia()
    uid = usuario_id_canonical()
    partes = [memoria_ficha.resumen(mem, uid)]
    partes += [f"Hecho: {h}" for h in hechos_verificados(mem)[:3]]
    partes += [f"Charla: {c}" for c in resumen_conversaciones(mem)[:2]]
    return "; ".join(partes)[:max(1, int(max_chars))]


def resumen_para_prompt(memoria=None, incluir_conversaciones=True):
    """Ánimo + bromas vigentes + solo datos aún no inyectados (sin escrituras)."""
    global _VISTOS_PENDIENTES
    _hidratar_ledger()
    mem = memoria if memoria is not None else _instancia()
    uid = usuario_id_canonical()
    ficha = memoria_ficha.resumen(mem, uid)
    hechos = hechos_verificados(mem)
    charlas = resumen_conversaciones(mem) if incluir_conversaciones else []
    obligatorios = []
    animo = _directriz_emocional(mem)
    if animo:
        obligatorios.append(animo[:160])
    obligatorios.extend(bromas_internas(mem))
    obligatorios.extend(semanticos_relevantes(mem))
    try:
        import ciclo_sueno_kaya
        seguimiento = ciclo_sueno_kaya.seguimiento_para_prompt(uid)
        if seguimiento:
            obligatorios.append(seguimiento)
    except Exception:
        pass
    presupuesto = max(80, _MAX_CHARS - len(ficha) - 2)
    with _bloqueo:
        _asegurar_dia(_LEDGER)
        vistos = list(_LEDGER["vistos"])
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
            if len("; ".join(bloques + [bloque])) > presupuesto:
                break
            bloques.append(bloque)
            aceptados.append(clave)
        if not hechos and not charlas:
            bloques.append("Memoria sin hechos guardados todavía (no inventes datos del usuario)")
        vistos.extend(aceptados)
        _LEDGER["vistos"] = vistos[-_MAX_VISTOS:]
        if aceptados:
            _VISTOS_PENDIENTES = True
    texto = f"{ficha}; " + "; ".join(bloques) if bloques else ficha
    return f"\n\n[Lo que ya sé de ti, sin repetirlo]: {texto[:_MAX_CHARS]}."


__all__ = [
    "hechos_verificados", "es_pregunta_kaya", "resumen_conversaciones", "bromas_internas",
    "registrar_turno", "registrar_par", "turnos_recientes", "semanticos_relevantes",
    "usuario_id_canonical", "historial_conversacion_activa", "resumen_estable",
    "registrar_despertar", "resetear_sesion", "resumen_para_prompt",
]
