"""Consultas acotadas reutilizadas por el grafo lógico."""
from memoria_grafo_utils import normalizar


def buscar_nodos(grafo, consulta, usuario_id=None, limite=20):
    uid = grafo._uid(usuario_id)
    q = set(normalizar(consulta).split())
    limite = max(1, min(int(limite), 100))
    if not q:
        return []
    with grafo._lock:
        filas = grafo.conexion.execute("SELECT * FROM entidades WHERE usuario_id=? ORDER BY id DESC LIMIT 500", (uid,)).fetchall()
    elegidos = [dict(r) for r in filas if q & set(r["nombre_norm"].split())]
    elegidos.sort(key=lambda r: (len(q & set(r["nombre_norm"].split())) / len(q), r["id"]), reverse=True)
    return elegidos[:limite]


def recorrer(grafo, nodo_id, usuario_id=None, max_profundidad=2, max_resultados=20):
    uid = grafo._uid(usuario_id); profundidad = max(0, min(int(max_profundidad), 5))
    limite = max(0, min(int(max_resultados), 100)); inicio = grafo.obtener_nodo(nodo_id, uid)
    if not inicio or not limite:
        return []
    vistos, cola, salida = {int(nodo_id)}, [(int(nodo_id), 0, [])], []
    while cola and len(salida) < limite:
        actual, nivel, camino = cola.pop(0)
        if nivel >= profundidad:
            continue
        for e in grafo.listar_relaciones(actual, uid, limite=limite):
            destino = e["destino_id"] if e["origen_id"] == actual else (e["origen_id"] if not e["dirigida"] else None)
            if destino is None or destino in vistos:
                continue
            vistos.add(destino); nodo = grafo.obtener_nodo(destino, uid)
            if nodo:
                ruta = camino + [e]
                salida.append({"nodo": nodo, "relacion": e, "camino": ruta, "profundidad": nivel+1})
                if len(salida) >= limite:
                    break
                cola.append((destino, nivel+1, ruta))
    return salida[:limite]


def relaciones_de_recuerdos(grafo, ids, usuario_id=None, confianza_min=.75, limite=12):
    uid = grafo._uid(usuario_id); ids = [int(x) for x in ids if x is not None][:100]
    if not ids:
        return []
    ph = ",".join("?" for _ in ids)
    sql = ("SELECT r.*,a.nombre AS nombre_origen,b.nombre AS nombre_destino FROM relaciones r "
           "JOIN entidades a ON a.id=r.origen_id AND a.usuario_id=r.usuario_id "
           "JOIN entidades b ON b.id=r.destino_id AND b.usuario_id=r.usuario_id "
           "WHERE r.usuario_id=? AND r.estado='activo' AND r.confianza>=? AND r.recuerdo_id IN ("+ph+") "
           "ORDER BY r.confianza DESC LIMIT ?")
    with grafo._lock:
        return [dict(x) for x in grafo.conexion.execute(sql,
            (uid, float(confianza_min), *ids, max(0, min(int(limite), 30)))).fetchall()]
