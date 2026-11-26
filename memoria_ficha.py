"""Ficha base compacta del usuario, reconstruida solo de datos explícitos."""
import re

_CAMPOS = (
    (r"\b(?:me llamo|mi nombre es)\s+([A-Za-zÁÉÍÓÚáéíóúÑñ][\wÁÉÍÓÚáéíóúÑñ'’-]{1,20}"
     r"(?:\s+[A-Za-zÁÉÍÓÚáéíóúÑñ][\wÁÉÍÓÚáéíóúÑñ'’-]{1,20}){0,2})", "Nombre"),
    (r"\b(?:estoy estudiando|estudio|estudia|estudios? de)\s+([\wÁÉÍÓÚáéíóúÑñ' -]{3,60})", "Estudios"),
    (r"\b(?:estoy trabajando en|trabajo en|mi proyecto es|proyecto activo)\s+([\wÁÉÍÓÚáéíóúÑñ' -]{3,60})", "Proyectos"),
    (r"\b(?:vivo en|estoy en|mi ciudad es)\s+([\wÁÉÍÓÚáéíóúÑñ' -]{3,40})", "Ubicación"),
    (r"\b(?:me gusta|me encanta|prefiero|le gusta|le encanta|prefiere)\s+([\wÁÉÍÓÚáéíóúÑñ' -]{3,60})", "Prefiere"),
)


def _principal():
    try:
        import memoria
        return memoria.instancia_principal()
    except Exception:
        return None


def _textos(memoria=None, usuario_id=None):
    mem = memoria if memoria is not None else _principal()
    uid = usuario_id or getattr(mem, "usuario_id", None)
    if not uid:
        try:
            import memoria_unificada
            uid = memoria_unificada.usuario_id_canonical()
        except Exception:
            uid = "local"
    salida = []
    if mem is not None:
        try:
            salida.extend(str(f.get("contenido") or "")
                          for f in mem.almacen.listar_recuerdos(400, usuario_id=uid))
        except Exception:
            pass
        try:
            salida.extend(str(h) for h in (mem.datos.get("hechos") or []))
        except Exception:
            pass
        try:
            usuario = str(mem.datos.get("usuario") or mem.datos.get("creador") or "").strip()
            if usuario:
                salida.append(f"Mi nombre es {usuario}")
        except Exception:
            pass
    return salida


def resumen(memoria=None, usuario_id=None, max_chars=180):
    """Devuelve siempre la ficha; si no hay datos, lo dice sin inventar."""
    partes = {}
    for texto in _textos(memoria, usuario_id):
        limpio = re.sub(r"\s+", " ", str(texto or "")).strip()
        for patron, etiqueta in _CAMPOS:
            if etiqueta in partes:
                continue
            coincidencia = re.search(patron, limpio, re.I)
            if coincidencia:
                valor = coincidencia.group(1).strip(" ,.;!?¿¡")
                if len(valor) >= 2:
                    partes[etiqueta] = valor[:32]
    if not partes:
        return "[Ficha: sin datos confirmados]"
    trozos = [f"{etiqueta}: {partes[etiqueta]}"
              for _patron, etiqueta in _CAMPOS if etiqueta in partes]
    texto = "[Ficha: " + " | ".join(trozos) + "]"
    limite = max(40, int(max_chars))
    return texto if len(texto) <= limite else texto[:limite - 4].rstrip(" |:") + "]"


__all__ = ["resumen"]
