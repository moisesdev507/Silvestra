"""Recuperación híbrida y trazable sobre las interfaces existentes de memoria."""
import math
from datetime import date

import memoria_busqueda as mb
import memoria_consulta
import memoria_embeddings as me
import memoria_indice_vectorial as miv
import memoria_tiempo as mt

SINONIMOS = dict(me.SINONIMOS)
NEGACION = {"no", "nunca", "ya_no", "dejo_de", "sin"}
PARES = (("usar", "evitar"), ("activo", "inactivo"), ("aceptar", "rechazar"),
         ("elegir", "descartar"), ("preferir", "evitar"), ("trabajar", "renunciar"))


def _palabras(texto):
    return set(mb.extraer_palabras_clave(str(texto or "")))


def _fecha(item):
    fecha_texto, _ = mt.extraer_fecha_de_recuerdo(item.get("contenido", ""))
    if fecha_texto:
        return fecha_texto
    valor = item.get("fecha_evento") or item.get("creado_en")
    try:
        return date.fromisoformat(str(valor)[:10])
    except (TypeError, ValueError):
        extraida, _ = mt.extraer_fecha_de_recuerdo(item.get("contenido", ""))
        return extraida


def _expandidos(terminos):
    salida = set(terminos)
    for termino in terminos:
        salida.update(SINONIMOS.get(termino, ()))
        if len(termino) >= 6:
            salida.add(termino[:-2])
    return salida - mb.STOPWORDS


def _calibrar(base):
    """Curva sigmoid suave: rompe el plano 0.40-0.46 sin aplanar extremos."""
    x = max(0.0, min(1.0, float(base)))
    try:
        y = 1.0 / (1.0 + math.exp(-10.0 * (x - 0.5)))
    except OverflowError:
        y = 0.0 if x < 0.5 else 1.0
    return round(0.15 * x + 0.85 * y, 4)


def _puntuacion(item, analisis, contexto, hoy, similitud=0.0):
    q, texto = set(analisis["terminos"]), _palabras(item.get("contenido"))
    expand = _expandidos(q)
    literal = len(q & texto) / max(1, len(q))
    sem = len(expand & texto) / max(1, len(expand))
    ctx = _palabras(contexto)
    alineacion = len(ctx & texto) / max(1, len(ctx)) if ctx else 0.0
    fecha = _fecha(item)
    dias = max(0, (hoy - fecha).days) if fecha else 365
    frescura = math.exp(-dias / 180.0)
    try:
        confianza = max(0.0, min(1.0, float(item.get("confianza", 0.5) or 0.0)))
    except (TypeError, ValueError):
        confianza = 0.0
    origen = item.get("origen", "inferido")
    procedencia = 1.0 if origen == "explicito" else .55 if origen == "inferido" else .65
    meta = item.get("metadatos", {})
    meta = meta if isinstance(meta, dict) else {}
    try:
        importancia = float(meta.get("importancia", meta.get("relevancia", .5)) or .5)
    except (TypeError, ValueError):
        importancia = .5
    importancia = max(0.0, min(1.0, importancia))
    afinidad = min(1.0, len(q & texto) / 3.0)
    sim = max(0.0, min(1.0, float(similitud or 0.0)))
    base = (.22*literal + .10*sem + .07*alineacion + .34*sim + .09*frescura
            + .08*confianza + .06*procedencia + .03*importancia + .01*afinidad)
    return _calibrar(base)


def _polaridad(texto):
    t = " " + mb.normalizar(texto) + " "
    neg = any(" " + n + " " in t for n in NEGACION)
    activos = set()
    palabras = _palabras(texto)
    for a, b in PARES:
        if a in palabras:
            activos.add(a)
        elif b in palabras:
            activos.add(b)
    return neg, activos


def _contradicciones(items):
    pares = []
    for i, a in enumerate(items):
        for b in items[i+1:]:
            wa, wb = _palabras(a.get("contenido")), _palabras(b.get("contenido"))
            if not (wa & wb):
                continue
            na, pa = _polaridad(a.get("contenido", ""))
            nb, pb = _polaridad(b.get("contenido", ""))
            opuestos = na != nb or any((x, y) in PARES or (y, x) in PARES for x in pa for y in pb)
            if opuestos:
                pares.append({"recuerdo_a": a, "recuerdo_b": b,
                              "estado": "posible_contradiccion"})
    return pares


def recuperar(gestor, consulta, usuario_id="local", contexto="", limite=5):
    limite = max(1, min(int(limite), 20))
    trabajo, error = [], None
    try:
        trabajo = gestor.listar_trabajo(usuario_id=usuario_id)
    except Exception as exc:
        error = type(exc).__name__
    analisis = memoria_consulta.analizar(consulta, usuario_id, trabajo, contexto)
    busqueda = analisis["consulta"]
    if analisis["resolucion"]:
        busqueda += " " + analisis["resolucion"]

    almacen = getattr(gestor, "almacen", None)
    tipo_vector = miv.tipo_dominante(almacen, usuario_id) if almacen is not None else 0
    q_vector = None
    vectoriales = []
    try:
        if almacen is not None:
            texto_vector = str(consulta or "") + " " + str(contexto or "")
            q_vector, _ = me.vector_consulta(
                texto_vector, analisis["terminos"], tipo_vector == me.TIPO_API)
        if q_vector is not None:
            vectoriales = miv.candidatos_vectoriales(
                almacen, q_vector, tipo_vector, usuario_id,
                limite=max(20, limite * 5))
    except Exception as exc:
        error = error or type(exc).__name__

    candidatos, vistos = [], set()
    try:
        for consulta_busqueda in (busqueda, " ".join(sorted(_expandidos(set(analisis["terminos"]))))) :
            if not consulta_busqueda.strip():
                continue
            for item in gestor.buscar(consulta_busqueda, limite=min(60, limite * 8), usuario_id=usuario_id):
                clave = ("db", item.get("id"))
                if clave not in vistos:
                    item["tipo_memoria"] = item.get("tipo_memoria", "semantica")
                    candidatos.append(item); vistos.add(clave)
            if len(candidatos) >= min(3, limite):
                break
        for item in trabajo:
            if item.usuario_id == usuario_id:
                candidatos.append({"id": item.clave, "usuario_id": item.usuario_id,
                    "contenido": str(item.contenido), "tipo_memoria": "trabajo",
                    "origen": "explicito", "confianza": .5, "categoria": "trabajo",
                    "fecha_evento": item.creado_en, "creado_en": item.creado_en,
                    "metadatos": {"volatil": True}})
    except Exception as exc:
        error = type(exc).__name__

    por_clave = {}
    for item in candidatos:
        rid = item.get("id")
        if isinstance(rid, int):
            por_clave[("db", rid)] = item
    for item in vectoriales:
        clave = ("db", item["id"])
        previo = por_clave.get(clave)
        if previo is not None:
            previo["similitud_vectorial"] = item["similitud_vectorial"]
        else:
            item.setdefault("tipo_memoria", "semantica")
            candidatos.append(item)
            por_clave[clave] = item

    hoy = mt.obtener_fecha_actual()
    inicio, fin = analisis["rango_temporal"] or (None, None)
    puntuados = []
    for item in candidatos:
        if item.get("usuario_id", usuario_id) != usuario_id:
            continue
        if item.get("estado", "activo") != "activo":
            continue
        f = _fecha(item)
        if inicio and (f is None or not (date.fromisoformat(inicio) <= f <= date.fromisoformat(fin))):
            continue
        similitud = item.get("similitud_vectorial", 0.0)
        item["puntuacion"] = _puntuacion(item, analisis, contexto, hoy, similitud)
        puntuados.append(item)
    preferidos = set(analisis["tipos"])
    puntuados.sort(key=lambda x: (x["puntuacion"], x.get("tipo_memoria") in preferidos,
                                  x.get("creado_en", "")), reverse=True)
    elegidos = puntuados[:limite]
    relaciones = []
    grafo = getattr(gestor, "grafo", None)
    ids = [x.get("id") for x in elegidos if isinstance(x.get("id"), int)]
    if grafo and ids:
        try:
            relaciones = grafo.relaciones_de_recuerdos(ids, usuario_id, .75, 8)
        except Exception as exc:
            error = error or type(exc).__name__
    cobertura = "insuficiente" if not elegidos or (analisis["ambigua"] and not analisis["resolucion"]) else "parcial" if elegidos[0]["puntuacion"] < .22 else "adecuada"
    return {"consulta": analisis, "resultados": elegidos, "contradicciones": _contradicciones(elegidos),
            "ambigua": analisis["ambigua"], "cobertura": cobertura,
            "sin_resultados": not bool(elegidos), "error_almacenamiento": error,
            "usuario_id": usuario_id, "relaciones": relaciones,
            "vectorial_disponible": q_vector is not None}


def formatear(paquete, limite_caracteres=1200):
    lineas = []
    if paquete.get("error_almacenamiento"):
        lineas.append("[Recuperación de memoria no disponible por un error de almacenamiento.]")
    if paquete.get("ambigua"):
        lineas.append("[Consulta ambigua: falta contexto para resolver la referencia.]")
    for r in paquete.get("resultados", []):
        fecha = str(r.get("fecha_evento") or "fecha desconocida")[:10]
        lineas.append(f"- ({r.get('tipo_memoria')}; {r.get('origen')}; confianza {float(r.get('confianza', 0)):.2f}; {fecha}) {r.get('contenido','')}")
    for c in paquete.get("contradicciones", []):
        a, b = c["recuerdo_a"], c["recuerdo_b"]
        lineas.append(f"[Posible contradicción: ({a.get('origen')}, {a.get('fecha_evento')}, {a.get('confianza')}) {a.get('contenido')} / ({b.get('origen')}, {b.get('fecha_evento')}, {b.get('confianza')}) {b.get('contenido')}]")
    if paquete.get("sin_resultados"):
        lineas.append("[Sin resultados en los recuerdos disponibles.]")
    elif paquete.get("cobertura") == "parcial":
        lineas.append("[Cobertura parcial; confirma antes de tratarlo como definitivo.]")
    return "\n".join(lineas)[:max(0, int(limite_caracteres))]

