"""Bus cognitivo único: contexto y post-turno compartidos por Live y Celeste.

Reúne los motores ya existentes sin duplicarlos. Todas las operaciones son
tolerantes a fallos y el arranque no imprime nada en el registro.
"""
import contextlib
import hashlib
import io
import threading

import cerebro_autonomo
import cerebro_grafo
import cerebro_rag
import cerebro_trabajo
import contexto_ambiental
import correcciones
import memoria_contexto
import memoria_semantica
import memoria_unificada


def inicializar_cerebro():
    """Crea de forma idempotente las tablas de grafo, RAG y embeddings."""
    estado = {}
    silencio = io.StringIO()
    with contextlib.redirect_stdout(silencio):
        pasos = (
            ("grafo", cerebro_grafo, "inicializar_grafo"),
            ("rag", cerebro_rag, "inicializar_rag"),
            ("arranque", memoria_unificada, "sincronizar_arranque"),
        )
        for nombre, modulo, funcion in pasos:
            try:
                getattr(modulo, funcion)()
                estado[nombre] = True
            except Exception:
                estado[nombre] = False
        for nombre, funcion in (("vectores", "_conectar"), ("embeddings", "_conectar_kaya")):
            try:
                con = getattr(memoria_semantica, funcion)()
                con.close()
                estado[nombre] = True
            except Exception:
                estado[nombre] = False
    return estado


def _sin_encabezado(texto):
    """Quita rótulos ajenos para que el bloque único no repita cabeceras."""
    limpio = str(texto or "").strip()
    if limpio.startswith("[CONOCIMIENTO VIVO DEL GRAFO]"):
        partes = limpio.split("\n", 1)
        limpio = partes[1] if len(partes) > 1 else ""
    return limpio.strip()


def _sin_duplicados(texto):
    vistos, salida = set(), []
    for linea in str(texto or "").splitlines():
        limpia = linea.strip()
        if not limpia or limpia in vistos:
            continue
        vistos.add(limpia)
        salida.append(limpia)
    return "\n".join(salida)


def compilar_contexto_unico(consulta="", max_chars=2200, estable=False):
    """Devuelve un único bloque compacto y sin duplicados para Live y Celeste."""
    limite = max(200, int(max_chars))
    try:
        if estable:
            ficha = memoria_contexto.resumen_estable(max_chars=430)
        else:
            ficha = memoria_contexto.resumen_para_prompt()
    except Exception:
        ficha = ""
    try:
        grafo = cerebro_grafo.consultar_contexto_grafo(consulta, limite=6) if consulta else ""
    except Exception:
        grafo = ""
    try:
        correcciones_txt = correcciones.resumen_para_prompt(consulta)
    except Exception:
        correcciones_txt = ""
    try:
        trabajo = cerebro_trabajo.resumen_contexto_trabajo()
    except Exception:
        trabajo = ""
    try:
        ambiente = contexto_ambiental.resumen_para_prompt()
    except Exception:
        ambiente = ""
    try:
        turnos = memoria_contexto.historial_conversacion_activa(12, 1200)
    except Exception:
        turnos = []
    hilo = "\n".join(
        f"{'Usuario' if t.get('role') == 'user' else 'Kaya'}: {t.get('content', '')}"
        for t in turnos if t.get("content")
    )

    trabajo_ambiente = "\n".join(x for x in (trabajo, ambiente) if x)
    titulo_hilo = "Conversación reciente en curso" if estable else "Hilo reciente"
    try:
        tono = cerebro_autonomo.linea_estado_atencion()
    except Exception:
        tono = ""
    secciones = (
        ("Estado emocional y atención", tono),
        ("Ficha y recuerdos del usuario", ficha),
        ("Grafo de relaciones", _sin_encabezado(grafo)),
        ("Correcciones activas", correcciones_txt),
        ("Contexto de trabajo y ambiente", trabajo_ambiente),
        (titulo_hilo, hilo),
    )
    bloques = [f"[{titulo}]\n{_sin_duplicados(cuerpo)}" for titulo, cuerpo in secciones if cuerpo]
    texto = "\n\n".join(bloques)
    if len(texto) > limite:
        recortado = texto[:limite]
        texto = recortado.rsplit("\n", 1)[0].rstrip() if "\n" in recortado else recortado.rstrip()
    return texto


def _ultima_respuesta():
    """Texto de Kaya inmediatamente anterior al turno que se está procesando."""
    try:
        historial = memoria_contexto.historial_conversacion_activa(12, 1200)
    except Exception:
        return ""
    for turno in reversed(historial[:-1]):
        if turno.get("role") != "user" and turno.get("content"):
            return str(turno["content"])
    return ""


def _id_turno(texto, origen):
    return "turno_" + hashlib.sha1((origen + "|" + texto).encode("utf-8")).hexdigest()[:20]


def _indexar_embeddings(texto, origen):
    """Asegura un vector real para el turno relevante sin bloquear la respuesta."""
    if len(str(texto or "").strip()) < 8:
        return False
    try:
        vector = memoria_semantica.vectorizar(texto, permitir_online=False)
        if not vector:
            return False
        return bool(memoria_semantica.indexar_recuerdo_kaya(
            _id_turno(texto, origen), texto, usuario_id=memoria_contexto.usuario_id_canonical()))
    except Exception:
        return False


def _post_usuario(texto, origen):
    """Ejecuta grafo, autoaprendizaje, embeddings y correcciones en daemon."""
    limpio = str(texto or "").strip()
    hilos = {}
    corregida = False
    if not limpio:
        return {"correccion": corregida, "hilos": hilos}
    try:
        cerebro_trabajo.resolver_referencias(limpio)
    except Exception:
        pass
    try:
        if correcciones.es_correccion(limpio):
            correcciones.registrar_correccion(_ultima_respuesta(), limpio)
            corregida = True
    except Exception:
        pass
    try:
        hilos["grafo"] = threading.Thread(
            target=cerebro_grafo.extraer_y_guardar_hechos, args=(limpio,),
            daemon=True, name="cerebro-grafo-turno")
        hilos["grafo"].start()
    except Exception:
        pass
    try:
        hilos["memoria"] = memoria_unificada.aprender_del_turno_async(
            limpio, canal="voz" if origen == "live" else "texto")
    except Exception:
        pass
    try:
        hilos["embeddings"] = threading.Thread(
            target=_indexar_embeddings, args=(limpio, origen),
            daemon=True, name="cerebro-embeddings-turno")
        hilos["embeddings"].start()
    except Exception:
        pass
    try:
        cerebro_autonomo.notificar_actividad(origen)
    except Exception:
        pass
    return {"correccion": corregida, "hilos": hilos}


def procesar_turno_cognitivo(rol, texto, origen="live"):
    """Registra un turno de Live o Celeste y dispara el pipeline cognitivo."""
    papel = "user" if str(rol or "").lower() in ("user", "usuario", "tú") else "kaya"
    try:
        memoria_contexto.registrar_turno(papel, texto)
    except Exception:
        pass
    if papel != "user":
        return {"correccion": False, "hilos": {}}
    return _post_usuario(texto, origen)


def procesar_par_cognitivo(texto_usuario, texto_kaya, origen="celeste"):
    """Variante de Celeste: registra el par completo y procesa solo el usuario."""
    try:
        memoria_contexto.registrar_turno("user", texto_usuario, espejo=False)
        memoria_contexto.registrar_turno("kaya", texto_kaya, espejo=False)
    except Exception:
        pass
    return _post_usuario(texto_usuario, origen)


ejecutar_consolidacion_reposo = cerebro_autonomo.ejecutar_consolidacion_reposo
evaluar_atencion_proactiva = cerebro_autonomo.evaluar_atencion_proactiva

__all__ = [
    "inicializar_cerebro", "compilar_contexto_unico",
    "procesar_turno_cognitivo", "procesar_par_cognitivo",
    "ejecutar_consolidacion_reposo", "evaluar_atencion_proactiva",
]
