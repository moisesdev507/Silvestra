"""Gestión, conmutación y ejecución de proveedores LLM por tarea."""
import json
import threading
import requests

import acciones
import calidad_respuesta as cr
import proveedores_cadenas as pc
import proveedores_stream as ps
from sesion_http import obtener_sesion
from proveedores_validador import extraer_motivo, iniciar_validacion_segundo_plano, desactivar_modelo, desactivar_proveedor, esta_desactivado

_enfriamientos = {}
enfriamientos = _enfriamientos
_aviso_respaldo_pendiente = False
_ultimo_proveedor = "Groq"
_claves_anteriores = {}


def forzar_utf8(texto):
    """Garantiza que el texto esté en UTF-8 correcto y corrige secuencias Latin-1."""
    if not texto or not isinstance(texto, str):
        return texto or ""
    if any(c in texto for c in ("Ã", "Â", "â")):
        try:
            return texto.encode("latin-1").decode("utf-8")
        except Exception:
            pass
    return texto


def _registrar(mensaje):
    print(f"[tiempo] {mensaje}", flush=True)


def marcar_enfriamiento(nombre, modelo=None, headers=None, motivo=None):
    """Pone a un modelo o proveedor en pausa diferenciando TPM y TPD."""
    pc.marcar_enfriamiento(_enfriamientos, nombre, modelo, headers, motivo=motivo)


def proveedores_disponibles(tarea="charla"):
    """Devuelve la lista de proveedores configurados y disponibles para la tarea."""
    return pc.proveedores_disponibles(tarea, _enfriamientos, _claves_anteriores)


def _lanzar_reintento(tarea):
    pc.lanzar_reintento_segundo_plano(proveedores_disponibles, tarea)


def completar(mensajes, tarea="charla", timeout=20, max_tokens=None):
    global _aviso_respaldo_pendiente, _ultimo_proveedor
    candidatos = proveedores_disponibles(tarea)
    if not candidatos:
        _registrar("cerebro sin proveedores disponibles: modo emergencia local")
        _lanzar_reintento(tarea)
        return pc.respuesta_emergencia_local()

    if max_tokens is None:
        max_tokens = 550 if tarea in ("razonamiento", "pesado") else 260

    for prov in candidatos:
        nombre = prov["nombre"]
        url = f"{prov['base_url'].rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {prov['clave']}", "Content-Type": "application/json"}
        modelos = prov.get("modelos_activos") or prov.get("modelos", [])
        fallos_turno = 0
        proveedor_enfriado = False
        proveedor_fuera = False

        for modelo in list(modelos):
            if esta_desactivado(nombre, modelo):
                continue
            try:
                sesion = obtener_sesion()
                r = sesion.post(
                    url,
                    headers=headers,
                    json={"model": modelo, "messages": mensajes, "max_tokens": max_tokens},
                    timeout=timeout,
                )
                r.encoding = "utf-8"
                if r.status_code == 429:
                    mot = extraer_motivo(r, 429)
                    marcar_enfriamiento(nombre, modelo, r.headers, motivo=mot)
                    fallos_turno += 1
                    _registrar(f"cerebro 429 en {nombre} ({modelo}), pasando al siguiente modelo de la misma cuenta...")
                    continue
                if r.status_code == 503:
                    mot = extraer_motivo(r, 503)
                    marcar_enfriamiento(nombre, modelo, r.headers, motivo=mot)
                    marcar_enfriamiento(nombre, motivo=f"fallo_total_modelos en {nombre} ({mot})")
                    fallos_turno += 1
                    proveedor_enfriado = True
                    _registrar(f"cerebro HTTP 503 en {nombre} ({modelo}): enfriamiento breve, pasando al siguiente proveedor...")
                    break
                if r.status_code == 401:
                    desactivar_proveedor(nombre)
                    proveedor_fuera = True
                    _registrar(f"cerebro HTTP 401 en {nombre}: credencial rechazada, proveedor fuera de rotación")
                    break
                if r.status_code in (404, 410):
                    mot = extraer_motivo(r, r.status_code)
                    marcar_enfriamiento(nombre, modelo, r.headers, motivo=mot)
                    desactivar_modelo(nombre, modelo)
                    fallos_turno += 1
                    estado = "retirado y desactivado" if r.status_code == 410 else "desactivado"
                    _registrar(f"cerebro HTTP {r.status_code} en {nombre} ({modelo}): {mot} ({estado})")
                    continue
                if r.status_code != 200:
                    fallos_turno += 1
                    _registrar(f"cerebro HTTP {r.status_code} en {nombre} ({modelo}): {r.text[:80]}")
                    continue
                try:
                    datos = r.json()
                except Exception:
                    datos = json.loads(r.content.decode("utf-8", errors="replace"))

                contenido = forzar_utf8(datos["choices"][0]["message"].get("content") or "")
                if not contenido.strip():
                    continue

                # Control de calidad lingüística
                ok_c, mot_c = cr.analizar_calidad_texto(contenido, contexto_windows=mensajes)
                if not ok_c:
                    _registrar(f"filtro_calidad respuesta rechazada en {nombre} ({modelo}): {mot_c}. Reintentando...")
                    continue

                if tarea == "fondo":
                    _registrar(f"tarea_fondo proveedor={nombre} modelo={modelo}")
                else:
                    _registrar(f"respuesta proveedor={nombre} modelo={modelo}")

                _ultimo_proveedor = nombre
                return contenido
            except requests.exceptions.Timeout as ex:
                mot = f"timeout ({str(ex)[:60].strip()})"
                marcar_enfriamiento(nombre, modelo, motivo=mot)
                fallos_turno += 1
                _registrar(f"cerebro timeout en {nombre} ({modelo}): {mot}")
            except Exception as e:
                fallos_turno += 1
                _registrar(f"cerebro error en {nombre} ({modelo}): {e}")

        if fallos_turno and not proveedor_enfriado and not proveedor_fuera:
            marcar_enfriamiento(nombre, motivo=f"fallo_total_modelos en {nombre}")
        _registrar(f"cerebro agotados modelos en {nombre}, cambiando de proveedor")
        if nombre == "Groq" and _ultimo_proveedor == "Groq":
            _aviso_respaldo_pendiente = True

    _registrar("cerebro todos los proveedores fallaron: activando modo de emergencia local")
    _lanzar_reintento(tarea)
    return pc.respuesta_emergencia_local()


def completar_flujo(mensajes, al_frase, tarea="charla", timeout_paralelo=2.5, on_primer_token=None, on_emocion=None):
    """Interfaz unificada para streaming con conmutación limpia y control de calidad."""
    try:
        import cerebro_perfil
        p = cerebro_perfil.obtener_perfil()
        if p:
            p.marcar_despacho_llm()
    except Exception:
        pass
    candidatos = proveedores_disponibles(tarea)
    texto, prov_g, mod_g = ps.completar_flujo(
        mensajes,
        al_frase,
        tarea,
        candidatos,
        forzar_utf8_fn=forzar_utf8,
        marcar_enfriamiento_fn=marcar_enfriamiento,
        registrar_fn=_registrar,
        lanzar_reintento_fn=_lanzar_reintento,
        timeout_espera=timeout_paralelo,
        on_primer_token=on_primer_token,
        on_emocion=on_emocion,
    )
    global _ultimo_proveedor
    _ultimo_proveedor = prov_g
    return texto


def accion_estado_proveedores(app):
    def _tarea():
        texto_voz, texto_burbuja = pc.reporte_estado_proveedores(_enfriamientos)
        app.cola.put(("hablar_registro", (texto_voz, texto_burbuja)))
        print("[tiempo] Consulta de estado_proveedores completada.", flush=True)

    threading.Thread(target=_tarea, daemon=True).start()


def instalar(app):
    """Registra la acción estado_proveedores e inicia la validación de modelos remotos."""
    try:
        iniciar_validacion_segundo_plano()
    except Exception as e:
        _registrar(f"no se pudo iniciar validador de modelos: {e}")

    acciones.registrar(
        "estado_proveedores",
        lambda: accion_estado_proveedores(app),
        "informa el estado de los proveedores de IA (activos, enfriamiento o sin clave) y sus cadenas por tarea (úsala cuando pregunten 'cómo van los proveedores', 'estado de los proveedores', 'qué modelos están activos')",
    )
