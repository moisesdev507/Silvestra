"""Extracción conservadora, conflictos y consultas del grafo de conocimiento."""
import re

import memoria_grafo as mg
import memoria_busqueda as mb

PATRONES = (
    (r"(?P<a>.+?)\s+(?:usa|utiliza)\s+(?P<b>.+)", "utiliza"),
    (r"(?P<a>.+?)\s+depende\s+de\s+(?P<b>.+)", "depende_de"),
    (r"(?P<a>.+?)\s+es\s+parte\s+de\s+(?P<b>.+)", "es_parte_de"),
    (r"(?P<a>.+?)\s+est[aá]\s+relacionad[oa]\s+con\s+(?P<b>.+)", "esta_relacionado_con"),
    (r"(?P<a>.+?)\s+pertenece\s+a\s+(?P<b>.+)", "pertenece_a"),
    (r"(?P<a>.+?)\s+fue\s+creado\s+por\s+(?P<b>.+)", "fue_creado_por"),
    (r"(?P<a>.+?)\s+contribuye\s+a\s+(?P<b>.+)", "contribuye_a"),
    (r"(?P<a>.+?)\s+tiene\s+como\s+objetivo\s+(?P<b>.+)", "tiene_como_objetivo"),
    (r"(?P<a>.+?)\s+es\s+(?:una\s+)?versi[oó]n\s+de\s+(?P<b>.+)", "es_version_de"),
    (r"(?P<a>.+?)\s+es\s+consecuencia\s+de\s+(?P<b>.+)", "es_consecuencia_de"),
    (r"(?P<a>.+?)\s+ocurri[oó]\s+antes\s+de\s+(?P<b>.+)", "ocurrio_antes_de"),
    (r"(?P<a>.+?)\s+ocurri[oó]\s+despu[eé]s\s+de\s+(?P<b>.+)", "ocurrio_despues_de"),
)
TECNOLOGIAS = {"python", "sqlite", "sqlite3", "pyside6", "numpy", "whisper", "windows", "git", "fts5"}
INVERSAS = {"ocurrio_antes_de": "ocurrio_despues_de", "ocurrio_despues_de": "ocurrio_antes_de"}
FUNCIONALES = {"pertenece_a", "fue_creado_por", "tiene_como_objetivo"}


def _limpiar(texto):
    return re.sub(r"\s+", " ", str(texto or "").strip(" .,!¡?¿;:\"'"))[:160]


def _tipo(nombre, relacion=""):
    n = set(mb.extraer_palabras_clave(nombre))
    if n & TECNOLOGIAS:
        return "tecnologia"
    if relacion == "fue_creado_por":
        return "persona"
    if n & {"proyecto", "app", "aplicacion", "sistema", "silvestra"}:
        return "proyecto"
    if n & {"objetivo", "meta"}:
        return "objetivo"
    return "concepto"


def detectar_contradicciones(grafo, relacion, usuario_id=None):
    uid = usuario_id or relacion["usuario_id"]
    actuales = grafo.listar_relaciones(relacion["origen_id"], uid, limite=100)
    conflictos = []
    for otra in actuales:
        if otra["id"] == relacion["id"]:
            continue
        invertida = (relacion["tipo_relacion"] in INVERSAS and
            otra["tipo_relacion"] == INVERSAS[relacion["tipo_relacion"]] and
            otra["destino_id"] == relacion["origen_id"])
        cronologia_opuesta = (relacion["tipo_relacion"].startswith("ocurrio_") and
            otra["origen_id"] == relacion["destino_id"] and otra["destino_id"] == relacion["origen_id"])
        incompatible = (relacion["tipo_relacion"] == otra["tipo_relacion"] and
            relacion["tipo_relacion"] in FUNCIONALES and otra["destino_id"] != relacion["destino_id"])
        if invertida or cronologia_opuesta or incompatible:
            conflictos.append(otra)
            grafo.actualizar_relacion(otra["id"], uid, estado="contradicho")
    if conflictos:
        grafo.actualizar_relacion(relacion["id"], uid, estado="contradicho")
    return conflictos


def registrar(grafo, origen, tipo_relacion, destino, usuario_id="local", recuerdo_id=None,
              explicit=False, confianza=.6, origen_dato=None, dirigida=True):
    nivel = max(0.0, min(1.0, float(confianza)))
    fuente = "explicita" if explicit else "inferida"
    if not explicit:
        nivel = min(nivel, .65)
    a = grafo.crear_nodo(_limpiar(origen), _tipo(origen), usuario_id)
    b = grafo.crear_nodo(_limpiar(destino), _tipo(destino, tipo_relacion), usuario_id)
    if not dirigida and b["id"] < a["id"]:
        a, b = b, a
    previa = any(r["origen_id"] == a["id"] and r["destino_id"] == b["id"] and
        r["tipo_relacion"] == tipo_relacion and r["recuerdo_id"] == recuerdo_id and
        r["dirigida"] == int(bool(dirigida)) and r["origen"] == fuente and
        r["origen_dato"] == origen_dato
        for r in grafo.listar_relaciones(a["id"], usuario_id, estado=None))
    fila = grafo.crear_relacion(a["id"], tipo_relacion, b["id"], usuario_id,
        dirigida, fuente, nivel, recuerdo_id=recuerdo_id, origen_dato=origen_dato)
    relacion = dict(fila)
    conflictos = detectar_contradicciones(grafo, relacion, usuario_id)
    estado_actual = grafo.listar_relaciones(a["id"], usuario_id, estado=None)
    relacion = next((r for r in estado_actual if r["id"] == relacion["id"]), relacion)
    antiguas = [r for r in estado_actual if r["id"] != relacion["id"] and
        r["tipo_relacion"] == tipo_relacion and r["origen_id"] == a["id"] and
        r["destino_id"] != b["id"] and tipo_relacion in FUNCIONALES]
    return {"relacion": relacion, "duplicada": previa,
            "contradicciones": conflictos, "posiblemente_desactualizadas": antiguas}


def extraer_desde_recuerdo(grafo, contenido, usuario_id="local", recuerdo_id=None,
                           origen_memoria="inferido", confianza=.6):
    texto = re.sub(r"^\[\d{4}-\d{2}-\d{2}\]\s*", "", str(contenido or ""))
    for patron, tipo in PATRONES:
        m = re.search(patron, texto, re.I)
        if not m:
            continue
        a, b = _limpiar(m.group("a")), _limpiar(m.group("b"))
        if len(a) < 2 or len(b) < 2 or mg.normalizar(a) == mg.normalizar(b):
            return []
        out = registrar(grafo, a, tipo, b, usuario_id, recuerdo_id,
                        origen_memoria == "explicito", confianza, "memoria")
        if recuerdo_id is not None:
            n_rec = grafo.crear_nodo(texto[:150], "recuerdo", usuario_id)
            rel = out["relacion"]
            for endpoint in (rel["origen_id"], rel["destino_id"]):
                grafo.crear_relacion(n_rec["id"], "esta_relacionado_con", endpoint,
                    usuario_id, False, rel["origen"], rel["confianza"],
                    recuerdo_id=recuerdo_id, origen_dato="mencion_en_recuerdo")
        return [out]
    return []


def consultar_relacional(grafo, consulta, usuario_id="local", contexto="",
                         max_profundidad=2, max_resultados=20):
    max_profundidad = max(0, min(int(max_profundidad), 5))
    max_resultados = max(0, min(int(max_resultados), 100))
    texto = (str(consulta or "") + " " + str(contexto or "")).strip()
    nodos = grafo.buscar_nodos(texto, usuario_id, limite=10)
    relaciones, vistos = [], set()
    if len(nodos) >= 2:
        origen = nodos[0]
        destinos = {n["id"] for n in nodos[1:]}
        for item in grafo.recorrer(origen["id"], usuario_id, max_profundidad, max_resultados):
            if item["nodo"]["id"] in destinos:
                for e in item.get("camino", [item["relacion"]]):
                    if e["id"] not in vistos:
                        relaciones.append(e); vistos.add(e["id"])
        for e in grafo.listar_relaciones(origen["id"], usuario_id, estado=None, limite=max_resultados):
            if e["estado"] == "contradicho" and e["destino_id"] in destinos and e["id"] not in vistos:
                relaciones.append(e); vistos.add(e["id"])
    if nodos and (len(nodos) < 2 or not relaciones):
        for e in grafo.listar_relaciones(nodos[0]["id"], usuario_id, estado=None, limite=max_resultados):
            if e["estado"] in ("activo", "contradicho") and e["id"] not in vistos:
                relaciones.append(e); vistos.add(e["id"])
    conflictos = [r for r in relaciones if r.get("estado") == "contradicho"]
    ambiguo = not nodos or not relaciones
    return {"consulta": consulta, "usuario_id": usuario_id, "entidades": nodos,
            "relaciones": relaciones[:max_resultados], "ambigua": ambiguo,
            "contradicciones": conflictos, "cobertura": "insuficiente" if ambiguo else "adecuada"}
