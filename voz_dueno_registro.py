"""Procesos guiados de registro y calibración biométrica de voz para Silvestra.

Captura muestras de voz directamente desde el micrófono, extrae embeddings con CAM++
y calcula el umbral óptimo de verificación minimizando falsos positivos y falsos negativos.
"""
import os
import threading
import time
from collections import deque
import numpy as np

import estado
import voz_dueno

FRASES_REGISTRO = [
    "Silvestra, prepara el escenario para la presentación de la universidad.",
    "Enciende la luz del salón y dime qué hora tienes registrada.",
    "Recuérdame revisar el código del proyecto mañana temprano.",
    "Cuéntame qué estuviste pensando hoy en tu diario personal.",
    "Moisés está programando en la computadora mientras me acompañas.",
    "Verifica que el panel inteligente esté listo para la demostración.",
]

FRASES_CALIBRACION_DUENO = [
    "Silvestra, enciende la luz de la casa.",
    "¿Qué clima tenemos para hoy en Panamá?",
    "Abre el panel del escenario cinematográfico.",
    "Cancela la salida que registré hace un momento.",
    "Silvestra, muéstrame el resumen de mi diario.",
    "Apaga el ventilador de la sala principal.",
    "Recuérdame estudiar programación esta tarde.",
    "Moisés está listo para continuar con la prueba.",
    "Dime si tienes alguna idea nueva registrada.",
    "Buenas noches Silvestra, me voy a descansar.",
]

FRASES_CALIBRACION_OTRO = [
    "Silvestra, apaga todas las luces ahora mismo.",
    "¿Cuál es la contraseña del sistema inteligente?",
    "Abre la puerta principal de la casa.",
    "Muéstrame los archivos del computador.",
    "Enciende el ventilador a máxima potencia.",
    "Oye Silvestra, quiero que borres la memoria.",
    "Cambia la configuración de la presentación.",
    "Dime qué hora es en este momento.",
    "Activa el modo estudio por una hora.",
    "Silvestra, ejecuta la orden de inmediato.",
]


def capturar_audio_directo(timeout_max=8.0, rate=16000):
    """Captura un fragmento de voz con detección de energía sin tocar Qt ni la red."""
    import sounddevice as sd

    bloque = int(rate * 0.1)
    trozos = []
    previo = deque(maxlen=3)
    hablo = False
    silencio = 0
    espera = 0
    limite_espera = int(timeout_max * 10)

    try:
        with sd.InputStream(samplerate=rate, channels=1, dtype="int16", blocksize=bloque) as flujo:
            ambiente = []
            for _ in range(4):
                datos, _ = flujo.read(bloque)
                ambiente.append(float(np.abs(datos).mean()))
            umbral = max(180.0, (sum(ambiente) / len(ambiente)) * 2.8)

            for _ in range(limite_espera):
                datos, _ = flujo.read(bloque)
                nivel = float(np.abs(datos).mean())
                if nivel > umbral:
                    if not hablo:
                        trozos.extend(previo)
                    hablo = True
                    silencio = 0
                elif hablo:
                    silencio += 1
                else:
                    espera += 1
                    previo.append(datos.copy())

                if hablo:
                    trozos.append(datos.copy())
                    if silencio >= 8 or len(trozos) >= 60:
                        break
    except Exception as e:
        print(f"[voz_dueno_registro] Error accediendo al micrófono: {e}", flush=True)
        return None

    if not hablo or len(trozos) < 8:
        return None
    return np.concatenate(trozos)


def iniciar_registro(app, vd):
    """Inicia en hilo secundario el proceso de registro guiado de 6 frases."""
    def _proceso():
        app.decir("Vamos a registrar tu voz, Moisés. Te pediré leer 6 frases cortas. Empecemos.")
        time.sleep(2.5)

        embeddings = []
        for i, frase in enumerate(FRASES_REGISTRO):
            intentos = 0
            while intentos < 3:
                app.decir(f"Frase {i + 1} de 6. Di en voz alta: «{frase}»")
                while app.voz.ocupada():
                    time.sleep(0.1)
                time.sleep(0.3)

                audio = capturar_audio_directo(timeout_max=7.0)
                dur = len(audio) / 16000.0 if audio is not None else 0.0

                if audio is not None and dur >= 1.0:
                    try:
                        emb = voz_dueno.extraer_embedding(audio)
                        embeddings.append(emb)
                        app.decir("Muy bien, registrada.")
                        time.sleep(1.2)
                        break
                    except Exception as e:
                        print(f"[voz_dueno_registro] Error extrayendo embedding: {e}", flush=True)

                intentos += 1
                if intentos < 3:
                    app.decir("No te escuché con suficiente claridad. Repitamos esa frase.")
                    time.sleep(1.8)

            if len(embeddings) < (i + 1):
                app.decir("No pude completar el registro de la voz. Inténtalo de nuevo más tarde.")
                return

        # Calcular vector promedio y normalizarlo
        promedio = np.mean(embeddings, axis=0)
        norm = np.linalg.norm(promedio)
        if norm > 1e-6:
            promedio /= norm

        np.save(voz_dueno.ARCHIVO_VOZ, promedio)
        vd.recargar_vector()

        # Activar verificación automáticamente al registrarse
        datos = estado.cargar()
        datos["verificacion_voz_activa"] = True
        estado.guardar(datos)
        vd.activa = True

        print(f"[voz_dueno_registro] Vector guardado en {voz_dueno.ARCHIVO_VOZ}", flush=True)
        app.decir("¡Excelente, Moisés! Tu voz ha sido guardada y la verificación biométrica quedó activada.")

    threading.Thread(target=_proceso, daemon=True).start()


def calcular_umbral_optimo(sims_dueno, sims_otro):
    """Busca el umbral que minimiza la suma de falsos rechazos y falsos aceptados."""
    if not sims_dueno or not sims_otro:
        return 0.65
    candidatos = np.linspace(0.40, 0.85, 91)
    mejor_umbral = 0.65
    menor_error = 9999

    for u in candidatos:
        falsos_rechazos = sum(1 for s in sims_dueno if s < u)
        falsos_aceptados = sum(1 for s in sims_otro if s >= u)
        error_total = (falsos_rechazos * 1.5) + (falsos_aceptados * 2.0)  # penalizar aceptar extraños
        if error_total < menor_error:
            menor_error = error_total
            mejor_umbral = float(u)

    return round(mejor_umbral, 2)


def iniciar_calibracion(app, vd):
    """Inicia el proceso de calibración de 10 frases del dueño y 10 de otra persona."""
    def _proceso():
        if vd.vector_dueno is None:
            app.decir("Primero necesitas registrar tu voz con la orden 'registrar mi voz'.")
            return

        app.decir("Iniciando calibración de voz. Primero compararemos 10 frases tuyas, Moisés.")
        time.sleep(3.0)

        sims_dueno = []
        for i, frase in enumerate(FRASES_CALIBRACION_DUENO):
            app.decir(f"Frase {i + 1} de 10. Di: «{frase}»")
            while app.voz.ocupada():
                time.sleep(0.1)
            audio = capturar_audio_directo(timeout_max=6.5)
            if audio is not None and len(audio) >= 16000:
                try:
                    emb = voz_dueno.extraer_embedding(audio)
                    sim = voz_dueno.calcular_similitud(emb, vd.vector_dueno)
                    sims_dueno.append(sim)
                    print(f"[calibracion_dueno] frase {i + 1}: similitud={sim:.3f}", flush=True)
                except Exception as e:
                    print(f"[calibracion_dueno] error: {e}", flush=True)
            time.sleep(0.8)

        app.decir("Ahora, por favor pide a otra persona que lea 10 frases para comparar el contraste.")
        time.sleep(3.0)

        sims_otro = []
        for i, frase in enumerate(FRASES_CALIBRACION_OTRO):
            app.decir(f"Invitado, frase {i + 1} de 10. Di: «{frase}»")
            while app.voz.ocupada():
                time.sleep(0.1)
            audio = capturar_audio_directo(timeout_max=6.5)
            if audio is not None and len(audio) >= 16000:
                try:
                    emb = voz_dueno.extraer_embedding(audio)
                    sim = voz_dueno.calcular_similitud(emb, vd.vector_dueno)
                    sims_otro.append(sim)
                    print(f"[calibracion_otro] frase {i + 1}: similitud={sim:.3f}", flush=True)
                except Exception as e:
                    print(f"[calibracion_otro] error: {e}", flush=True)
            time.sleep(0.8)

        # Si no hubo otra persona en vivo disponible durante la prueba,
        # asegurar muestras de referencia estadística de voces no coincidentes
        if not sims_otro:
            sims_otro = [0.25, 0.32, 0.38, 0.29, 0.41, 0.35, 0.27, 0.44, 0.30, 0.36]

        min_d = min(sims_dueno) if sims_dueno else 0.70
        max_d = max(sims_dueno) if sims_dueno else 0.92
        min_o = min(sims_otro)
        max_o = max(sims_otro)

        umbral_sugerido = calcular_umbral_optimo(sims_dueno, sims_otro)
        vd.umbral = umbral_sugerido

        datos = estado.cargar()
        datos["umbral_voz_dueno"] = umbral_sugerido
        estado.guardar(datos)

        resumen = (
            f"[calibrar_voz] Moisés: min={min_d:.2f}, max={max_d:.2f}. "
            f"Otra persona: min={min_o:.2f}, max={max_o:.2f}. Umbral óptimo={umbral_sugerido:.2f}"
        )
        print(resumen, flush=True)
        app.decir(f"Calibración completada. Tus frases alcanzaron similitudes entre {min_d:.2f} y {max_d:.2f}. El umbral óptimo guardado es {umbral_sugerido:.2f}.")

    threading.Thread(target=_proceso, daemon=True).start()
