"""Puente del bucle agéntico al flujo real de voz/chat, sin tocar Qt."""
import re
import threading

import acciones
import agente_bucle as ab
import agente_confirmacion as ac
import agente_conector_plan as cp
import agente_permisos as ap
import agente_traza as at

_CHARLA = frozenset("hola hi que tal como estas gracias adios buenos dias buenas noches bien mal ok cierto exacto supuesto".split())
_OPER = frozenset("abre abrir busca buscar crea crear escribe escribir guarda guardar lee leer llea llee recuerda recuerdame recordatorio avisame borra borrar elimina eliminar envia enviar manda ejecuta ejecutar operacion proceso activar activa sube baja silencia descarga aprende confirmar lista".split())
_ESTADO = {"activo": True, "ttl": ac.TTL_CONFIRMACION_SEG}
_BLOQUEO = threading.RLock()
_ACTIVOS = {}


def configurar(activo=None, ttl=None):
    """Activa/desactiva el conector y ajusta el TTL de confirmación."""
    with _BLOQUEO:
        if activo is not None:
            _ESTADO["activo"] = bool(activo)
        if ttl is not None:
            try:
                _ESTADO["ttl"] = min(max(0.01, float(ttl)), ac.TTL_MAXIMO_SEG)
            except (TypeError, ValueError):
                pass


def activo():
    return bool(_ESTADO["activo"])


def debe_intervenir(texto):
    """Bypass de charla pura: decide sin construir el bucle."""
    if not activo():
        return False
    palabras = set(re.findall(r"[a-záéíóúñ]+", str(texto or "").strip().lower()))
    if palabras and palabras <= _CHARLA:
        return False
    return bool(palabras & _OPER)


def _hacer(nombre, argumentos, app, indice, pasos, ejecutados):
    texto = argumentos.get("texto", argumentos.get("arg"))
    i = min(max(indice["actual"], 0), len(pasos) - 1)
    try:
        if nombre == "poner_recordatorio":
            gestor = getattr(app, "recordatorios", None)
            if not callable(getattr(gestor, "poner_recordatorio", None)):
                import recordatorios
                gestor = recordatorios.Recordatorios(app)
                if app is not None:
                    app.recordatorios = gestor
            ok, mensaje = True, gestor.poner_recordatorio(texto)
            ok = "No entendí" not in str(mensaje)
        else:
            ok, mensaje = acciones.ejecutar(nombre, texto)
    except Exception as error:
        ok, mensaje = False, f"Error al ejecutar: {error}"
    ejecutados[i] = (nombre, bool(ok), str(mensaje or ""))
    if ok:
        indice["actual"] += 1
    return bool(ok), str(mensaje or "")


def atender(cerebro, texto, al_frase=None, app=None, canal=None,
            interactivo=None, ttl=None):
    """Ejecuta la orden con el bucle agéntico; devuelve None si no aplica."""
    if app is None:
        app = getattr(cerebro, "app", None)
    if not debe_intervenir(texto):
        return None
    pasos = cp.planificar(texto)
    if not pasos:
        return None

    traza = at.Traza()
    clave = id(app) if app is not None else 0
    with _BLOQUEO:
        _ACTIVOS[clave] = traza
    indice, ejecutados = {"actual": 0}, {}

    def confirmar(nombre, descripcion, datos):
        espera = _ESTADO["ttl"] if ttl is None else ttl
        return ac.solicitar(app, nombre, descripcion, datos, canal=canal,
                            interactivo=interactivo, ttl=espera)

    def decidir(objetivo, observaciones, catalogo, paso):
        ultima = observaciones[-1] if observaciones else None
        if ultima is not None and not ultima.exito:
            nom, arg = pasos[min(indice["actual"], len(pasos) - 1)]
            if "|" not in str(arg) and "texto" in str(ultima.error).lower():
                arg = f"{arg} | {cp.contenido(objetivo)}"
            return {"herramienta": nom, "argumentos": {"texto": arg}, "intencion": "corregir_error"}
        i = indice["actual"]
        if i >= len(pasos):
            return {"final": True, "respuesta": "Listo."}
        nom, arg = pasos[i]
        return {"herramienta": nom, "argumentos": {"texto": arg}, "intencion": objetivo}

    bucle = ab.BucleAgente(
        catalogo=cp.catalogo(pasos),
        compuerta=ap.CompuertaPermisos(confirmar=confirmar),
        verificador=lambda nombre, obs, esperado: bool(obs.exito) and indice["actual"] >= len(pasos),
        max_pasos=min(5, len(pasos) + 2),
        ejecutar=lambda n, a, p: _hacer(n, a, app, indice, pasos, ejecutados),
        traza=traza)
    try:
        resultado = bucle.ejecutar(str(texto), decidir=decidir, cancelacion=traza.evento)
    finally:
        with _BLOQUEO:
            if _ACTIVOS.get(clave) is traza:
                del _ACTIVOS[clave]

    respuesta = cp.sintetizar(pasos, ejecutados, resultado, indice)
    herramientas = sorted({str(e.get("herramienta") or "") for e in resultado.traza if e.get("herramienta")})
    print(f"[agente] exito={int(resultado.exito)} pasos={resultado.pasos} "
          f"motivo={at._texto(resultado.motivo, 40)} herramientas={','.join(herramientas)[:120]}", flush=True)
    return respuesta, None, "alegre" if resultado.exito else "seria"


def cancelar(app):
    """Cancela confirmación pendiente y bucle activo de forma limpia."""
    ac.cancelar(app)
    clave = id(app) if app is not None else 0
    with _BLOQUEO:
        traza = _ACTIVOS.pop(clave, None)
    if traza is not None:
        traza.cancelar()
    return traza is not None
