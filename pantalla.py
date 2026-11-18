"""Módulo de visión de pantalla para Silvestra.

Captura la pantalla principal en un hilo secundario y en memoria (sin tocar disco),
la escala a un ancho máximo de 1280 px con JPEG calidad ~70, y la envía a los
modelos de visión de Groq con un timeout de 20 s por modelo (máximo ~40 s en total).
Todos los eventos hacia la interfaz pasan por app.cola para no congelar Qt.
"""
import base64
import io
import threading
import time
import traceback

from PIL import Image, ImageGrab

import acciones
import config


def capturar_pantalla_b64(ancho_max=1280, calidad=70):
    """Captura la pantalla principal dentro del hilo, la reduce y devuelve JPEG base64 en memoria."""
    img = ImageGrab.grab()
    if img.width > ancho_max:
        nuevo_alto = int(img.height * (ancho_max / img.width))
        img = img.resize((ancho_max, nuevo_alto), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format="JPEG", quality=calidad)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def analizar_pantalla(app, pregunta=None, hablar=True, al_terminar=None):
    """Ejecuta la captura y consulta de visión en segundo plano sin bloquear Qt."""
    t_total_inicio = time.time()
    # Indicador a la cola principal: NUNCA tocar Qt directamente desde este hilo
    app.cola.put(("mirando_pantalla", None))

    t_cap_inicio = time.time()
    try:
        b64 = capturar_pantalla_b64(ancho_max=1280, calidad=70)
        t_captura = time.time() - t_cap_inicio
    except Exception:
        print("[pantalla] Error capturando la pantalla:", flush=True)
        traceback.print_exc()
        msg_err = "No pude ver bien la pantalla, inténtalo otra vez."
        if hablar:
            app.cola.put(("hablar", msg_err))
        if al_terminar:
            try:
                al_terminar(msg_err)
            except Exception:
                pass
        return

    data_url = f"data:image/jpeg;base64,{b64}"
    consulta = (pregunta or "").strip()
    if not consulta:
        consulta = "Dime qué ves en mi pantalla y si hay algún error o detalle en el que me puedas ayudar."

    sistema = (
        f"Eres {app.memoria.nombre or 'Silvestra'}, asistente de {app.memoria.creador or 'tu creador'}.\n"
        "Estás viendo una captura de su pantalla porque te pidió expresamente que la miraras.\n"
        "Responde a su consulta con tu personalidad cálida, ingeniosa y cercana, en español panameño natural.\n"
        "Reglas obligatorias:\n"
        "1. Respuestas de 1 a 3 frases cortas, directas y aptas para ser leídas en voz alta.\n"
        "2. Sin listas, sin asteriscos, sin markdown, sin viñetas ni emojis.\n"
        "3. REGLA ESTRICTA DE PRIVACIDAD: Si en la pantalla aparece alguna contraseña, clave secreta, token, "
        "API key, tarjeta o dato confidencial, JAMÁS lo leas en voz alta ni digas el texto exacto. "
        "Solo avisa de forma prudente que ves una clave o contraseña sin revelar su contenido."
    )

    mensajes = [
        {"role": "system", "content": sistema},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": consulta},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]

    modelos = [config.MODELO_VISION] + [
        m for m in getattr(config, "MODELOS_VISION", []) if m != config.MODELO_VISION
    ]

    respuesta = None

    for modelo in modelos:
        tiempo_transcurrido = time.time() - t_total_inicio
        if tiempo_transcurrido >= 40.0:
            print(f"[pantalla] Tiempo total superó los 40 s ({tiempo_transcurrido:.1f}s), abortando búsqueda.", flush=True)
            break

        tiempo_restante = min(20.0, max(5.0, 40.0 - tiempo_transcurrido))
        t_req_inicio = time.time()
        try:
            r = app.cliente.chat.completions.create(
                model=modelo,
                messages=mensajes,
                max_tokens=250,
                temperature=0.7,
                timeout=tiempo_restante,
            )
            t_respuesta = time.time() - t_req_inicio
            texto = r.choices[0].message.content if r.choices else None
            if texto:
                respuesta = texto
                print(
                    f"[tiempo] vision modelo={modelo} captura={t_captura:.2f}s respuesta={t_respuesta:.2f}s",
                    flush=True,
                )
                break
        except Exception:
            print(f"[pantalla] Error con modelo de visión {modelo}:", flush=True)
            traceback.print_exc()

    if not respuesta:
        msg_err = "No pude ver bien la pantalla, inténtalo otra vez."
        if hablar:
            app.cola.put(("hablar", msg_err))
        if al_terminar:
            try:
                al_terminar(msg_err)
            except Exception:
                pass
        return

    limpio = respuesta.replace("*", "").replace("- ", "").replace("\n", " ").strip("\"' ")
    if hablar:
        app.cola.put(("hablar", limpio))
    if al_terminar:
        try:
            al_terminar(limpio)
        except Exception:
            pass


def instalar(app):
    """Registra la acción mirar_pantalla en acciones.py."""
    def accion_mirar(arg=None):
        threading.Thread(target=analizar_pantalla, args=(app, arg), daemon=True).start()

    acciones.registrar(
        "mirar_pantalla",
        accion_mirar,
        "captura la pantalla y la analiza con visión artificial para responder preguntas sobre lo que el usuario ve, código o errores. Escribe: ACCION: mirar_pantalla | pregunta o duda del usuario",
        con_texto=True,
    )
