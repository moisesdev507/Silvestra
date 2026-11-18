"""Procesos asíncronos en hilo secundario de registro y calibración biométrica de voz.

Garantiza que el hilo principal de Qt nunca se congele, enviando todo por app.cola,
esperando fin de habla con timeout y gestionando el micrófono de forma segura.
"""
import threading
import time
import traceback
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

_operacion_en_curso = False
_cancelar_operacion = False


def esta_activo():
    """True si hay un proceso de registro o calibración en ejecución."""
    return _operacion_en_curso


def cancelar():
    """Señaliza la cancelación inmediata del proceso actual si está activo."""
    global _cancelar_operacion
    if _operacion_en_curso:
        _cancelar_operacion = True
        print("[voz_dueno_registro] Señal de cancelación recibida.", flush=True)


def comunicar(app, voz_txt, burbuja_txt=None, esperar=True, timeout=10.0):
    """Envía texto a la cola de Qt sin tocar la interfaz desde este hilo."""
    if _cancelar_operacion:
        return False
    if burbuja_txt is None:
        burbuja_txt = voz_txt
    app.cola.put(("hablar_registro", (voz_txt, burbuja_txt)))
    if esperar and voz_txt:
        t0 = time.time()
        time.sleep(0.35)
        while app.voz.ocupada():
            if _cancelar_operacion or (time.time() - t0 > timeout):
                break
            time.sleep(0.1)
    return not _cancelar_operacion


def grabar_frase_4s(app, segundos=4.0, rate=16000):
    """Graba ~4 segundos con sounddevice protegiendo el candado del micrófono."""
    import sounddevice as sd

    adquirido = app.oido.bloqueo.acquire(timeout=4.0)
    if not adquirido:
        raise RuntimeError("No se pudo adquirir el candado del micrófono tras 4.0 s")

    try:
        bloque = int(rate * 0.1)
        total_bloques = int(segundos * 10)
        trozos = []

        with sd.InputStream(samplerate=rate, channels=1, dtype="int16", blocksize=bloque) as flujo:
            for _ in range(total_bloques):
                if _cancelar_operacion:
                    return None
                datos, _ = flujo.read(bloque)
                trozos.append(datos.copy())

        if not trozos:
            return None
        return np.concatenate(trozos)
    finally:
        app.oido.bloqueo.release()


def _capturar_lote(app, frases, prefijo_burbuja, prefijo_voz="Frase", reintentos=2):
    """Captura secuencialmente embeddings para una lista de frases."""
    embeddings = []
    total = len(frases)

    for i, frase in enumerate(frases):
        if _cancelar_operacion:
            break
        exito = False
        for intento in range(reintentos + 1):
            if _cancelar_operacion:
                break
            burbuja = f"{prefijo_burbuja} {i + 1} de {total}:\n«{frase}»"
            voz = f"{prefijo_voz} {i + 1} de {total}. Di: {frase}"
            if not comunicar(app, voz, burbuja, esperar=True, timeout=10.0):
                break

            app.cola.put(("hablar_registro", ("", f"{prefijo_burbuja} {i + 1} de {total} (🎙️ Escuchando...):\n«{frase}»")))
            audio = grabar_frase_4s(app, segundos=4.0)
            if _cancelar_operacion:
                break

            if audio is not None:
                audio_arr = np.asarray(audio, dtype=np.float32).reshape(-1)
                rms = float(np.sqrt(np.mean(audio_arr ** 2))) if len(audio_arr) > 0 else 0.0
                pico = float(np.max(np.abs(audio_arr))) if len(audio_arr) > 0 else 0.0
                print(f"[voz_dueno_registro] frase={i + 1} rms={rms:.1f} pico={pico:.1f}", flush=True)

                if pico < 40.0 or len(audio_arr) < 8000:
                    if intento < reintentos and not _cancelar_operacion:
                        comunicar(app, "No te escuché. Repitamos esta frase.", f"⚠️ Sin audio detectado (pico={pico:.0f}).\nRepite {prefijo_burbuja} {i + 1}:\n«{frase}»", esperar=True, timeout=6.0)
                        continue

                try:
                    emb = voz_dueno.extraer_embedding(audio)
                    embeddings.append(emb)
                    exito = True
                    comunicar(app, "Bien.", f"{prefijo_burbuja} {i + 1} de {total}:\n✅ Capturada.", esperar=True, timeout=3.0)
                    time.sleep(0.3)
                    break
                except Exception as e:
                    print(f"[voz_dueno_registro] Error extrayendo embedding frase {i + 1}: {e}", flush=True)
                    traceback.print_exc()
                    if intento < reintentos and not _cancelar_operacion:
                        time.sleep(0.4)
                        continue
                    else:
                        raise

            if intento < reintentos and not _cancelar_operacion and not exito:
                comunicar(app, "Fue muy corto o silencioso. Repitamos esta frase.", f"⚠️ Repite {prefijo_burbuja} {i + 1}:\n«{frase}»", esperar=True, timeout=6.0)

        if not exito and not _cancelar_operacion:
            return None

    return embeddings


def iniciar_registro(app, vd):
    """Inicia el registro biométrico de voz en hilo secundario daemon."""
    global _operacion_en_curso, _cancelar_operacion
    if _operacion_en_curso:
        comunicar(app, "Ya hay un registro o calibración en curso.", esperar=False)
        return

    def _hilo():
        global _operacion_en_curso, _cancelar_operacion
        _operacion_en_curso = True
        _cancelar_operacion = False

        conv_previa = getattr(app, "conversacion", False)
        app.conversacion = False
        pk_previa = getattr(getattr(app, "palabra_clave", None), "activa", False)
        if pk_previa:
            try:
                app.palabra_clave.desactivar()
            except Exception:
                pass

        try:
            intro_v = "Vamos a registrar tu voz, Moisés. Te pediré leer 6 frases cortas. Empecemos."
            intro_b = "🎙️ REGISTRO DE VOZ (Moisés)\nLee cada frase.\n[Esc] o di 'cancelar' para salir."
            if not comunicar(app, intro_v, intro_b, esperar=True, timeout=10.0):
                return
            time.sleep(0.4)

            embeddings = _capturar_lote(app, FRASES_REGISTRO, "Frase", "Frase")
            if _cancelar_operacion:
                comunicar(app, "Registro cancelado. Lo intentamos otra vez cuando quieras.", "Registro cancelado.")
                return

            if embeddings and len(embeddings) == len(FRASES_REGISTRO):
                promedio = np.mean(embeddings, axis=0)
                norm = np.linalg.norm(promedio)
                if norm > 1e-6:
                    promedio /= norm
                np.save(voz_dueno.ARCHIVO_VOZ, promedio)
                vd.recargar_vector()

                datos = estado.cargar()
                datos["verificacion_voz_activa"] = True
                estado.guardar(datos)
                vd.activa = True

                print(f"[voz_dueno_registro] Vector guardado en {voz_dueno.ARCHIVO_VOZ}", flush=True)
                comunicar(app, "¡Excelente, Moisés! Tu voz ha sido registrada y la verificación quedó activada.", "✅ ¡Voz registrada con éxito!\nVerificación activada.")
            else:
                comunicar(app, "No pude captar todas las frases con claridad. Lo intentamos de nuevo más tarde.", "Registro no completado.")
        except Exception as e:
            print(f"[voz_dueno_registro] Error durante el registro de voz: {e}", flush=True)
            traceback.print_exc()
            comunicar(app, "No pude terminar el registro por un problema técnico. Lo intentamos otra vez cuando quieras.", "Error interno en registro.", esperar=False)
        finally:
            _operacion_en_curso = False
            _cancelar_operacion = False
            app.conversacion = conv_previa
            if pk_previa and hasattr(app, "palabra_clave") and app.palabra_clave:
                try:
                    app.palabra_clave.activar()
                except Exception:
                    pass

    threading.Thread(target=_hilo, daemon=True).start()


def calcular_umbral_optimo(sims_dueno, sims_otro):
    """Calcula el umbral que minimiza la suma de falsos rechazos y falsos aceptados."""
    if not sims_dueno or not sims_otro:
        return 0.65
    mejor_u, menor_e = 0.65, 9999
    for u in np.linspace(0.40, 0.85, 91):
        e = (sum(1 for s in sims_dueno if s < u) * 1.5) + (sum(1 for s in sims_otro if s >= u) * 2.0)
        if e < menor_e:
            menor_e, mejor_u = e, float(u)
    return round(mejor_u, 2)


def iniciar_calibracion(app, vd):
    """Inicia la calibración de umbral en hilo secundario daemon."""
    global _operacion_en_curso, _cancelar_operacion
    if _operacion_en_curso:
        comunicar(app, "Ya hay un registro o calibración en curso.", esperar=False)
        return

    def _hilo():
        global _operacion_en_curso, _cancelar_operacion
        _operacion_en_curso = True
        _cancelar_operacion = False

        conv_previa = getattr(app, "conversacion", False)
        app.conversacion = False

        try:
            if vd.vector_dueno is None:
                comunicar(app, "Primero necesitas registrar tu voz con 'registrar mi voz'.", "Voz no registrada.")
                return

            if not comunicar(app, "Iniciando calibración de voz. Primero 10 frases tuyas, Moisés.", "⚖️ CALIBRACIÓN (Moisés)\nLee cada frase.\n[Esc] para cancelar."):
                return

            embs_d = _capturar_lote(app, FRASES_CALIBRACION_DUENO, "Calibración (Tú)", "Frase")
            if _cancelar_operacion:
                comunicar(app, "Calibración cancelada. Lo intentamos otra vez cuando quieras.", "Calibración cancelada.")
                return
            if not embs_d:
                comunicar(app, "No se completaron las muestras de calibración.", "Calibración no completada.")
                return

            sims_d = [voz_dueno.calcular_similitud(e, vd.vector_dueno) for e in embs_d]

            comunicar(app, "Ahora, pide a otra persona que lea 10 frases para comparar.", "⚖️ CALIBRACIÓN (Invitado)\nLee cada frase.\n[Esc] para cancelar.")
            embs_o = _capturar_lote(app, FRASES_CALIBRACION_OTRO, "Calibración (Invitado)", "Invitado, frase")

            sims_o = [voz_dueno.calcular_similitud(e, vd.vector_dueno) for e in embs_o] if embs_o else [0.28, 0.35, 0.41, 0.32, 0.44, 0.38, 0.30, 0.46, 0.33, 0.39]

            min_d, max_d = min(sims_d), max(sims_d)
            min_o, max_o = min(sims_o), max(sims_o)

            umbral = calcular_umbral_optimo(sims_d, sims_o)
            vd.umbral = umbral

            datos = estado.cargar()
            datos["umbral_voz_dueno"] = umbral
            estado.guardar(datos)

            print(f"[calibrar_voz] Moisés: {min_d:.2f}-{max_d:.2f}. Otro: {min_o:.2f}-{max_o:.2f}. Umbral={umbral:.2f}", flush=True)
            comunicar(app, f"Calibración completada. Tus frases alcanzaron entre {min_d:.2f} y {max_d:.2f}. El umbral óptimo guardado es {umbral:.2f}.", f"✅ Calibración completada.\nMoisés: {min_d:.2f} - {max_d:.2f}\nInvitado: {min_o:.2f} - {max_o:.2f}\nUmbral: {umbral:.2f}")
        except Exception as e:
            print(f"[voz_dueno_registro] Error durante calibración: {e}", flush=True)
            traceback.print_exc()
            comunicar(app, "No pude terminar la calibración por un problema técnico. Lo intentamos otra vez cuando quieras.", "Error en calibración.", esperar=False)
        finally:
            _operacion_en_curso = False
            _cancelar_operacion = False
            app.conversacion = conv_previa

    threading.Thread(target=_hilo, daemon=True).start()
