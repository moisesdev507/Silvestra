"""Módulo de aprendizaje continuo y perfil de conversación para Silvestra.

Orquesta la reflexión nocturna en hilo secundario (9 PM o al cerrar)
y registra las acciones del usuario para consultar, olvidar o borrar datos.
"""
import atexit
import datetime
import threading
import time

from PySide6.QtWidgets import QApplication

import acciones
import aprendizaje_datos as ad
import proveedores

# Reexportar funciones públicas para uso directo desde otros módulos
resumen_para_prompt = ad.resumen_para_prompt
registrar_interaccion = ad.registrar_interaccion
log = ad.log


class GestorAprendizaje:
    """Orquesta la reflexión nocturna, acciones de usuario y mantenimiento del perfil."""

    def __init__(self, app):
        self.app = app
        self._bloqueo = threading.RLock()
        self._detener = threading.Event()
        self.ultima_reflexion = ad.cargar_perfil().get("ultima_reflexion")

        app_qt = QApplication.instance()
        if app_qt:
            try:
                app_qt.aboutToQuit.connect(self.al_cerrar)
            except Exception:
                pass
        atexit.register(self.al_cerrar)

        self._hilo = threading.Thread(target=self._bucle_horario, daemon=True, name="AprendizajeHorario")
        self._hilo.start()

    def al_cerrar(self):
        """Ejecuta la reflexión nocturna al cerrar si no se ha realizado hoy."""
        hoy_str = datetime.date.today().strftime("%Y-%m-%d")
        if self.ultima_reflexion != hoy_str:
            self.ejecutar_reflexion_nocturna(forzar=False)

    def _bucle_horario(self):
        """Verifica cada minuto si es hora de reflexionar (a partir de las 9:00 PM)."""
        while not self._detener.is_set():
            try:
                ahora = datetime.datetime.now()
                hoy_str = ahora.strftime("%Y-%m-%d")
                if ahora.hour >= 21 and self.ultima_reflexion != hoy_str:
                    self.ejecutar_reflexion_nocturna(forzar=False)
            except Exception as e:
                log(f"Error en bucle horario: {e}")
            time.sleep(60)

    def ejecutar_reflexion_nocturna(self, forzar=False):
        """Envía las conversaciones al cerebro para actualizar perfil_conversacion.json."""
        def _tarea():
            with self._bloqueo:
                hoy_str = datetime.date.today().strftime("%Y-%m-%d")
                if not forzar and self.ultima_reflexion == hoy_str:
                    return

                convs = ad.cargar_conversaciones()
                if not convs:
                    log("Sin conversaciones registradas para reflexionar.")
                    if forzar:
                        self.app.cola.put(("hablar", "No hay conversaciones recientes registradas para analizar."))
                    return

                lineas_dialogo = []
                for fecha in sorted(convs.keys())[-7:]:
                    lineas_dialogo.append(f"--- DÍA {fecha} ---")
                    for t in convs[fecha][-15:]:
                        lineas_dialogo.append(f"Moisés ({t.get('hora', '')}): {t.get('usuario', '')}")
                        lineas_dialogo.append(f"Silvestra [{t.get('emocion', 'neutral')}]: {t.get('respuesta', '')}")

                charla_txt = "\n".join(lineas_dialogo)
                if not charla_txt.strip():
                    log("Conversaciones vacías tras filtrado.")
                    return

                sistema = (
                    "Eres el módulo de aprendizaje reflexivo de Silvestra, asistente IA de Moisés en Panamá.\n"
                    "Analiza las conversaciones recientes de Moisés para actualizar su perfil de interacción.\n\n"
                    "REGLAS ESTRICTAS DE PRIVACIDAD Y ÉTICA:\n"
                    "1. Analiza ÚNICAMENTE lo que Moisés dijo expresamente. Cero suposiciones.\n"
                    "2. JAMÁS hagas conjeturas ni deducciones sobre su salud física, mental o emocional, ni sobre dinero o contraseñas.\n"
                    "3. Para hilos abiertos: detecta planes futuros concretos con fecha (ej. 'mañana tengo examen', 'el viernes viajo').\n\n"
                    "Devuelve EXCLUSIVAMENTE un JSON válido con esta estructura:\n"
                    "{\n"
                    '  "estilo": {\n'
                    '    "palabras_y_apodos": ["palabras o modismos recurrentes"],\n'
                    '    "muletillas": ["muletillas o expresiones frecuentes"],\n'
                    '    "formalidad": "breve descripción de su formalidad",\n'
                    '    "largo_tipico": "breve descripción del largo de sus frases"\n'
                    '  },\n'
                    '  "costumbres_y_horarios": ["rutinas o costumbres que él mencionó"],\n'
                    '  "hilos_abiertos": [\n'
                    '    {"tema": "evento o asunto pendiente", "fecha": "YYYY-MM-DD o vacio"}\n'
                    '  ],\n'
                    '  "bromas_y_referencias": ["bromas o referencias compartidas"]\n'
                    "}"
                )

                prompt = f"Conversaciones recientes:\n{charla_txt[-4000:]}"
                try:
                    resp_llm = proveedores.completar([
                        {"role": "system", "content": sistema},
                        {"role": "user", "content": prompt},
                    ])
                except Exception as e:
                    log(f"Proveedores no disponibles al reflexionar: {e}. Se pospone.")
                    if forzar:
                        self.app.cola.put(("hablar", "No pude conectar con los proveedores de lenguaje para reflexionar ahora mismo."))
                    return

                nuevo = ad.extraer_json_robusto(resp_llm)
                if not nuevo or not isinstance(nuevo, dict):
                    log("No se pudo interpretar el JSON devuelto por el modelo.")
                    return

                perfil = ad.cargar_perfil()

                # Actualizar estilo
                n_estilo = nuevo.get("estilo", {})
                if isinstance(n_estilo, dict):
                    pal = list(dict.fromkeys(perfil["estilo"].get("palabras_y_apodos", []) + n_estilo.get("palabras_y_apodos", [])))
                    mul = list(dict.fromkeys(perfil["estilo"].get("muletillas", []) + n_estilo.get("muletillas", [])))
                    perfil["estilo"]["palabras_y_apodos"] = pal[-10:]
                    perfil["estilo"]["muletillas"] = mul[-6:]
                    if n_estilo.get("formalidad"):
                        perfil["estilo"]["formalidad"] = str(n_estilo["formalidad"]).strip()[:80]
                    if n_estilo.get("largo_tipico"):
                        perfil["estilo"]["largo_tipico"] = str(n_estilo["largo_tipico"]).strip()[:80]

                # Actualizar costumbres
                n_cost = nuevo.get("costumbres_y_horarios", [])
                if isinstance(n_cost, list):
                    comb_cost = list(dict.fromkeys(perfil.get("costumbres_y_horarios", []) + [str(c).strip() for c in n_cost if c]))
                    perfil["costumbres_y_horarios"] = comb_cost[-8:]

                # Actualizar bromas y referencias
                n_brom = nuevo.get("bromas_y_referencias", [])
                if isinstance(n_brom, list):
                    comb_brom = list(dict.fromkeys(perfil.get("bromas_y_referencias", []) + [str(b).strip() for b in n_brom if b]))
                    perfil["bromas_y_referencias"] = comb_brom[-8:]

                # Actualizar hilos abiertos preservando estados anteriores
                hilos_previos = perfil.get("hilos_abiertos", [])
                temas_existentes = {h.get("tema", "").lower(): h for h in hilos_previos}
                siguiente_id = max([h.get("id", 0) for h in hilos_previos] or [0]) + 1

                n_hilos = nuevo.get("hilos_abiertos", [])
                if isinstance(n_hilos, list):
                    for nh in n_hilos:
                        if not isinstance(nh, dict):
                            continue
                        tema = str(nh.get("tema", "")).strip()
                        if not tema:
                            continue
                        if tema.lower() in temas_existentes:
                            previo = temas_existentes[tema.lower()]
                            if nh.get("fecha"):
                                previo["fecha"] = nh.get("fecha")
                        else:
                            hilos_previos.append({
                                "id": siguiente_id,
                                "tema": tema,
                                "fecha": nh.get("fecha", ""),
                                "preguntado": False,
                                "cerrado": False,
                                "esperando_respuesta": False,
                            })
                            siguiente_id += 1

                perfil["hilos_abiertos"] = hilos_previos[-10:]
                perfil["ultima_reflexion"] = hoy_str
                self.ultima_reflexion = hoy_str

                ad.guardar_perfil(perfil)
                log(f"Reflexión nocturna completada con éxito para la fecha {hoy_str}.")
                if forzar:
                    self.app.cola.put(("hablar", "He completado la reflexión y actualizado tu perfil de conversación."))

        threading.Thread(target=_tarea, daemon=True).start()

    def accion_que_has_aprendido(self):
        """Lee en voz alta y muestra en la burbuja lo aprendido en el perfil."""
        def _tarea():
            perfil = ad.cargar_perfil()
            estilo = perfil.get("estilo", {})
            palabras = estilo.get("palabras_y_apodos", [])
            muletillas = estilo.get("muletillas", [])
            costumbres = perfil.get("costumbres_y_horarios", [])
            bromas = perfil.get("bromas_y_referencias", [])
            hilos = [h for h in perfil.get("hilos_abiertos", []) if not h.get("cerrado")]

            if not any([palabras, muletillas, costumbres, bromas, hilos]):
                self.app.cola.put(("hablar", "Todavía no he recopilado suficientes datos para armar tu perfil de conversación. Al final del día haré mi reflexión nocturna."))
                return

            voz_partes = []
            form = estilo.get("formalidad", "informal")
            largo = estilo.get("largo_tipico", "frases cortas")
            voz_partes.append(f"He aprendido que sueles comunicarte en un tono {form}, con {largo}.")
            if palabras:
                voz_partes.append(f"Sueles usar expresiones como {', '.join(palabras[:3])}.")
            if costumbres:
                voz_partes.append(f"Tengo presente costumbres tuyas como {costumbres[0]}.")
            if hilos:
                voz_partes.append(f"Y tengo pendiente seguir el tema de «{hilos[0].get('tema')}».")

            voz_txt = " ".join(voz_partes)

            burbuja_lineas = ["🧠 PERFIL DE CONVERSACIÓN APRENDIDO:"]
            burbuja_lineas.append(f"• Estilo: Tono {form} | {largo}")
            if palabras:
                burbuja_lineas.append(f"• Palabras frecuentes: {', '.join(palabras)}")
            if muletillas:
                burbuja_lineas.append(f"• Muletillas: {', '.join(muletillas)}")
            if costumbres:
                burbuja_lineas.append(f"• Costumbres: {'; '.join(costumbres)}")
            if bromas:
                burbuja_lineas.append(f"• Bromas y referencias: {'; '.join(bromas)}")
            if hilos:
                burbuja_lineas.append("• Hilos abiertos:")
                for h in hilos[:4]:
                    f_str = f" [{h.get('fecha')}]" if h.get("fecha") else ""
                    burbuja_lineas.append(f"   - #{h.get('id')}: {h.get('tema')}{f_str}")

            burbuja_txt = "\n".join(burbuja_lineas)
            self.app.cola.put(("hablar_registro", (voz_txt, burbuja_txt)))
            log("Consulta de perfil aprendida mostrada al usuario.")

        threading.Thread(target=_tarea, daemon=True).start()

    def accion_olvidar_aprendizaje(self, tema):
        """Elimina un dato concreto del perfil (tema, palabra, costumbre o hilo)."""
        def _tarea():
            if not tema or not str(tema).strip():
                self.app.cola.put(("hablar", "Dime qué dato o tema deseas que olvide de tu perfil."))
                return

            borrado = ad.eliminar_del_perfil(str(tema).strip())
            if borrado:
                log(f"Dato olvidado del perfil: {tema}")
                self.app.cola.put(("hablar", f"Listo Moisés, olvidé lo que había aprendido sobre {tema}."))
            else:
                self.app.cola.put(("hablar", f"No encontré ningún dato guardado sobre «{tema}» en tu perfil."))

        threading.Thread(target=_tarea, daemon=True).start()

    def accion_borrar_perfil(self, arg):
        """Borra todo el perfil y el historial de conversaciones tras confirmación."""
        def _tarea():
            texto = (arg or "").strip().lower()
            if texto in ("confirmar", "confirmar borrar perfil", "si", "sí"):
                ad.reiniciar_perfil_y_conversaciones()
                self.ultima_reflexion = None
                log("Perfil de conversación y conversaciones borrados por completo tras confirmación.")
                self.app.cola.put(("hablar", "He borrado por completo tu perfil de conversación y el registro de conversaciones."))
                return

            self.app.cola.put((
                "hablar",
                "Esta acción borrará todo lo que he aprendido de tu estilo, costumbres e hilos. Para confirmar, di o escribe: borrar perfil | confirmar."
            ))

        threading.Thread(target=_tarea, daemon=True).start()


def instalar(app):
    """Instala el módulo de aprendizaje y registra las acciones correspondientes."""
    gestor = GestorAprendizaje(app)
    app.aprendizaje = gestor

    acciones.registrar(
        "que_has_aprendido",
        lambda: gestor.accion_que_has_aprendido(),
        "Muestra y lee en voz alta un resumen del perfil y estilo aprendido de las conversaciones.",
    )
    acciones.registrar(
        "olvidar_aprendizaje",
        lambda arg: gestor.accion_olvidar_aprendizaje(arg),
        "Elimina un dato concreto o tema del perfil de aprendizaje. Lleva texto con el tema o dato a borrar.",
        con_texto=True,
    )
    acciones.registrar(
        "borrar_perfil",
        lambda arg=None: gestor.accion_borrar_perfil(arg),
        "Borra todo el perfil aprendido pidiendo confirmación previa. Si lleva texto 'confirmar', procede a borrar.",
        con_texto=True,
    )
    acciones.registrar(
        "reflexionar_aprendizaje",
        lambda arg=None: gestor.ejecutar_reflexion_nocturna(forzar=True),
        "Fuerza la reflexión nocturna para actualizar el perfil de conversación de inmediato con el cerebro.",
    )

    log("Módulo de aprendizaje continuo instalado.")
    return gestor
