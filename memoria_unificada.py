"""Fachada única de memoria persistente para Gemini Live y Celeste.

Unifica identidad, migración, consulta y auto-aprendizaje sin crear copias de
Memoria ni tocar Qt. Todo lo que se guarda son datos explícitos del usuario;
las inferencias y saludos quedan fuera por memoria_filtro.
"""
import json
import os
import re
import threading

import estado
import memoria_filtro
import memoria_modelos
import rutas_app

_lock = threading.RLock()
_sincronizados = set()

# Solo afirmaciones en primera persona: nunca suposiciones ni comandos.
_PATRONES = (
    (r"\b(?:me llamo|mi nombre es)\s+([A-Za-zÁÉÍÓÚáéíóúÑñ][\wÁÉÍÓÚáéíóúÑñ'’-]{1,20}"
     r"(?:\s+[A-Za-zÁÉÍÓÚáéíóúÑñ][\wÁÉÍÓÚáéíóúÑñ'’-]{1,20}){0,2})", "Mi nombre es {v}"),
    (r"\b(?:estoy estudiando|estudio|estudios? de)\s+([\wÁÉÍÓÚáéíóúÑñ' -]{3,60})", "Estudio {v}"),
    (r"\b(?:estoy trabajando en|trabajo en|mi proyecto es)\s+([\wÁÉÍÓÚáéíóúÑñ' -]{3,60})", "Trabajo en {v}"),
    (r"\b(?:vivo en|estoy en|mi ciudad es)\s+([\wÁÉÍÓÚáéíóúÑñ' -]{3,40})", "Vivo en {v}"),
    (r"\b(?:me gusta|me encanta|prefiero)\s+([\wÁÉÍÓÚáéíóúÑñ' -]{3,60})", "Me gusta {v}"),
)


def _principal():
    """Instancia real compartida; nunca crea una memoria nueva."""
    try:
        import memoria
        return memoria.instancia_principal()
    except Exception:
        return None


def usuario_id_canonical():
    """Único usuario_id para Live y Celeste (principal, estado.json o local)."""
    mem = _principal()
    if mem is not None:
        valor = getattr(mem, "usuario_id", "")
        try:
            return memoria_modelos.validar_usuario_id(valor)
        except Exception:
            pass
    try:
        datos = estado.cargar()
        for clave in ("usuario_id", "id_usuario", "perfil_id", "creador", "nombre_usuario"):
            valor = str(datos.get(clave) or "").strip()
            if valor:
                valor = re.sub(r"\s+", ".", valor)[:128]
                try:
                    return memoria_modelos.validar_usuario_id(valor)
                except Exception:
                    continue
    except Exception:
        pass
    return "local"


def sincronizar_arranque(usuario_id=None, forzar=False):
    """Idempotente: asegura JSON→SQLite y drena la cola de Supabase."""
    uid = usuario_id or usuario_id_canonical()
    with _lock:
        if uid in _sincronizados and not forzar:
            return {"ya_aplicada": True, "usuario_id": uid}
        _sincronizados.add(uid)
    mem = _principal()
    if mem is not None and mem.usuario_id != uid:
        uid = mem.usuario_id
    pendientes = 0
    try:
        import memoria_supabase as sb
        pendientes = int(sb.sincronizar_pendientes() or 0)
    except Exception:
        pass
    return {"ya_aplicada": False, "usuario_id": uid, "enviados": pendientes}


def recordar(hecho, texto_usuario="", canal="texto", fuente="auto_aprendizaje", **extra):
    """Guarda un hecho en la memoria compartida con el id canónico."""
    dato = str(hecho or "").strip()
    if not dato or memoria_filtro.es_ruido_extraccion(dato):
        return False
    mem = _principal()
    if mem is None:
        return False
    if getattr(mem, "bloqueo_invitado", False):
        return False
    kwargs = {
        "origen": "explicito",
        "texto_usuario": texto_usuario or dato,
        "fuente": fuente,
        "canal": canal,
    }
    kwargs.update(extra)
    kwargs.pop("usuario_id", None)  # La instancia principal ya usa el id canónico.
    try:
        return bool(mem.recordar(dato, **kwargs))
    except Exception:
        return False


def _rutas_json(mem, uid):
    rutas = []
    if mem is not None and getattr(mem, "ruta_json", None):
        rutas.append(mem.ruta_json)
    for base in (rutas_app.ruta_usuario("datos", "memoria.json"),
                 rutas_app.ruta_usuario("memoria.json")):
        if base not in rutas:
            rutas.append(base)
    return rutas


def _filas_json(mem, uid):
    salida = []
    for ruta in _rutas_json(mem, uid):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                datos = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(datos, dict):
            continue
        for hecho in datos.get("hechos", []):
            if isinstance(hecho, str) and hecho.strip():
                salida.append({"contenido": hecho.strip(), "fuente": "json"})
        for nombre, texto in (datos.get("resumenes_tematicos") or {}).items():
            if isinstance(texto, str) and texto.strip():
                salida.append({"contenido": f"{nombre}: {texto.strip()}", "fuente": "json"})
    return salida


def _filas_sqlite(mem, uid):
    if mem is None:
        return []
    try:
        filas = mem.almacen.listar_recuerdos(500, usuario_id=uid)
    except Exception:
        try:
            filas = mem.almacen.listar_recuerdos(500)
        except Exception:
            return []
    return [{"contenido": str(f.get("contenido") or ""), "fuente": "sqlite"}
            for f in filas if str(f.get("contenido") or "").strip()]


def _filas_supabase(uid):
    try:
        import memoria_supabase as sb
        filas = sb.consultar(uid, limite=100) or []
    except Exception:
        return []
    return [{"contenido": str(f.get("contenido") or ""), "fuente": "supabase"}
            for f in filas if isinstance(f, dict) and str(f.get("contenido") or "").strip()]


def consultar(tema=None, limite=5, usuario_id=None):
    """Consulta SQLite + JSON legado + Supabase sin duplicados."""
    uid = usuario_id or usuario_id_canonical()
    sincronizar_arranque(uid)
    mem = _principal()
    if mem is not None and mem.usuario_id != uid:
        uid = mem.usuario_id
    filas = _filas_sqlite(mem, uid) + _filas_json(mem, uid) + _filas_supabase(uid)
    tokens = [memoria_filtro.normalizar_para_filtro(t)
              for t in re.findall(r"\w+", str(tema or ""), re.UNICODE) if len(t) > 2]
    vistos, salida = set(), []
    for fila in filas:
        texto = fila["contenido"]
        clave = memoria_filtro.normalizar_para_filtro(texto)
        if not clave or clave in vistos:
            continue
        norm = clave
        if tokens and not any(tok.casefold() in norm for tok in tokens):
            continue
        vistos.add(clave)
        salida.append(f"Hecho: {_limpio(texto)}")
        if len(salida) >= max(1, int(limite)):
            break
    return "\n".join(salida) if salida else "No tengo recuerdos guardados sobre eso."


def _limpio(texto, max_len=160):
    return re.sub(r"\s+", " ", re.sub(r"^\[[^\]]+\]\s*", "", str(texto or ""))).strip()[:max_len]


def candidatos(texto):
    """Hechos explícitos extraídos del turno del usuario, sin inferencias."""
    limpio = re.sub(r"\s+", " ", str(texto or "").strip())
    if not limpio or memoria_filtro.es_ruido_extraccion(limpio):
        return []
    salida = []
    for patron, plantilla in _PATRONES:
        for coincidencia in re.finditer(patron, limpio, re.I):
            valor = re.sub(r"\s+", " ", coincidencia.group(1)).strip(" ,.;!?¿¡")
            if len(valor) < 2:
                continue
            hecho = plantilla.format(v=valor)
            if len(hecho) < 12 or memoria_filtro.es_ruido_extraccion(hecho):
                continue
            if hecho not in salida:
                salida.append(hecho)
            if len(salida) >= 4:
                return salida
    return salida


def aprender_del_turno(texto_usuario, canal="texto"):
    """Extracción síncrona: devuelve la lista de hechos realmente guardados."""
    guardados = []
    for hecho in candidatos(texto_usuario):
        if recordar(hecho, texto_usuario=texto_usuario, canal=canal,
                    fuente="auto_aprendizaje", contexto="turno del usuario"):
            guardados.append(hecho)
    return guardados


def aprender_del_turno_async(texto_usuario, canal="texto"):
    """Lanza la extracción en daemon ligero; devuelve el hilo para pruebas."""
    def tarea():
        try:
            aprender_del_turno(texto_usuario, canal)
        except Exception:
            pass
    hilo = threading.Thread(target=tarea, daemon=True, name="memoria-autoaprendizaje")
    hilo.start()
    return hilo


__all__ = [
    "usuario_id_canonical", "sincronizar_arranque", "recordar", "consultar",
    "candidatos", "aprender_del_turno", "aprender_del_turno_async",
]
