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

    def accion_reflexionar_ahora(self):
        """Acción disparada a mano para ejecutar la reflexión sobre las conversaciones."""
        self.ejecutar_reflexion_nocturna(forzar=True)

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
                        self.app.cola.put(("hablar", "No tengo conversaciones guardadas todavía para analizar. Habla conmigo hoy y haré mi reflexión."))
                    return

                total_convs = sum(len(lista) for lista in convs.values())
                total_dias = len(convs)

                lineas_dialogo = []
                for fecha in sorted(convs.keys())[-7:]:
                    lineas_dialogo.append(f"--- DÍA {fecha} ---")
                    for t in convs[fecha][-15:]:
                        lineas_dialogo.append(f"Moisés ({t.get('hora', '')}): {t.get('usuario', '')}")
                        lineas_dialogo.append(f"Silvestra [{t.get('emocion', 'neutral')}]: {t.get('respuesta', '')}")

                charla_txt = "\n".join(lineas_dialogo)
                if not charla_txt.strip():
                    log(f"Conversaciones vacías tras filtrado. Procesó 0 conversaciones.")
                    if forzar:
                        self.app.cola.put(("hablar", "No encontré texto de conversación útil para reflexionar."))
                    return

                sistema = (
                    "Eres el módulo de aprendizaje reflexivo de Silvestra, asistente IA en Panamá.\n"
                    "Analiza las charlas recientes para actualizar el perfil de interacción de Moisés.\n"
                    "REGLAS ÉTICAS: Analiza ÚNICAMENTE lo dicho expresamente. Cero suposiciones. Cero salud o claves.\n"
                    "Para hilos abiertos: detecta planes futuros concretos con fecha (ej. 'mañana tengo examen').\n"
                    "Devuelve SOLO este JSON válido:\n"
                    "{\n"
                    '  "estilo": {"palabras_y_apodos": [], "muletillas": [], "formalidad": "", "largo_tipico": ""},\n'
                    '  "costumbres_y_horarios": [],\n'
                    '  "hilos_abiertos": [{"tema": "", "fecha": ""}],\n'
                    '  "bromas_y_referencias": []\n'
                    "}"
                )

                prompt = f"Conversaciones recientes:\n{charla_txt[-4000:]}"
                try:
                    resp_llm = proveedores.completar([
                        {"role": "system", "content": sistema},
                        {"role": "user", "content": prompt},
                    ], tarea="fondo")
                except Exception as e:
                    log(f"Proveedores no disponibles al reflexionar: {e}. Se pospone.")
                    if forzar:
                        self.app.cola.put(("hablar", "No pude conectar con el cerebro para hacer la reflexión ahora mismo."))
                    return

                nuevo = ad.extraer_json_robusto(resp_llm)
                if not nuevo or not isinstance(nuevo, dict):
                    log(f"No se pudo interpretar el JSON devuelto por el modelo. Procesó {total_convs} conversaciones de {total_dias} días.")
                    if forzar:
                        self.app.cola.put(("hablar", "Revisé las conversaciones pero no pude interpretar los datos para el perfil."))
                    return

                perfil, campos = ad.actualizar_perfil_con_analisis(nuevo, hoy_str)
                self.ultima_reflexion = hoy_str

                # Log obligatorio con prefijo [aprendizaje], cantidad de conversaciones y campos
                campos_txt = ", ".join(campos) if campos else "ninguno (perfil al día)"
                log(f"Reflexión completada: procesó {total_convs} conversaciones de {total_dias} días. Campos actualizados: {campos_txt}.")

                if forzar:
                    estilo = perfil.get("estilo", {})
                    palabras = estilo.get("palabras_y_apodos", [])
                    costumbres = perfil.get("costumbres_y_horarios", [])
                    hilos = [h for h in perfil.get("hilos_abiertos", []) if not h.get("cerrado")]

                    if not campos:
                        msg = "Terminé mi reflexión sobre nuestras conversaciones. Tu perfil ya estaba al día y no encontré datos nuevos."
                    else:
                        frases = []
                        if "estilo" in campos and palabras:
                            frases.append(f"noté que sueles usar expresiones como '{palabras[-1]}'")
                        if "costumbres" in campos and costumbres:
                            frases.append(f"registré tu costumbre sobre {costumbres[-1]}")
                        if "hilos_abiertos" in campos and hilos:
                            frases.append(f"tengo presente el hilo sobre '{hilos[-1].get('tema')}'")
                        if "bromas" in campos and perfil.get("bromas_y_referencias"):
                            frases.append(f"guardé la referencia de '{perfil['bromas_y_referencias'][-1]}'")

                        det = ", y ".join(frases[:2]) if frases else f"actualicé {campos_txt} en tu perfil"
                        msg = f"Terminé mi reflexión: {det}." if frases else f"Terminé mi reflexión y {det}."

                    self.app.cola.put(("hablar", msg))

        threading.Thread(target=_tarea, daemon=True).start()

    def accion_que_has_aprendido(self):
        """Lee en voz alta y muestra en la burbuja lo aprendido en el perfil y los hilos abiertos."""
        def _tarea():
            perfil = ad.cargar_perfil()
            estilo = perfil.get("estilo", {})
            palabras = estilo.get("palabras_y_apodos", [])
            muletillas = estilo.get("muletillas", [])
            costumbres = perfil.get("costumbres_y_horarios", [])
            bromas = perfil.get("bromas_y_referencias", [])
            hilos_perfil = [h for h in perfil.get("hilos_abiertos", []) if not h.get("cerrado")]

            # Consultar también hilos.py
            hilos_pendientes = []
            try:
                import hilos as m_hilos
                for d in m_hilos.cargar():
                    if d.get("estado", "abierto") == "abierto" and d.get("texto"):
                        hilos_pendientes.append(d["texto"])
            except Exception:
                pass

            tiene_datos = any([palabras, muletillas, costumbres, bromas, hilos_perfil, hilos_pendientes])
            if not tiene_datos:
                self.app.cola.put(("hablar", "Todavía no tengo nada aprendido sobre ti ni hilos abiertos registrados. Conversa conmigo y haré mi reflexión al final del día."))
                return

            voz_partes = []
            form = estilo.get("formalidad", "informal")
            largo = estilo.get("largo_tipico", "frases cortas")
            if palabras or costumbres or hilos_perfil:
                voz_partes.append(f"He aprendido que sueles comunicarte en tono {form}, con {largo}.")
            if palabras:
                voz_partes.append(f"Usas expresiones como {', '.join(palabras[:3])}.")
            if costumbres:
                voz_partes.append(f"Tengo presente costumbres como {costumbres[0]}.")
            if hilos_perfil:
                voz_partes.append(f"Tengo abierto el hilo sobre «{hilos_perfil[0].get('tema')}».")
            elif hilos_pendientes:
                voz_partes.append(f"Tengo pendiente el tema de «{hilos_pendientes[0]}».")

            voz_txt = " ".join(voz_partes) if voz_partes else "He aprendido sobre tu estilo pero aún no tengo detalles específicos."

            burbuja_lineas = [
                "🧠 PERFIL DE CONVERSACIÓN APRENDIDO:",
                f"• Estilo: Tono {form} | {largo}",
            ]
            if palabras:
                burbuja_lineas.append(f"• Palabras frecuentes: {', '.join(palabras)}")
            if muletillas:
                burbuja_lineas.append(f"• Muletillas: {', '.join(muletillas)}")
            if costumbres:
                burbuja_lineas.append(f"• Costumbres: {'; '.join(costumbres)}")
            if bromas:
                burbuja_lineas.append(f"• Bromas y referencias: {'; '.join(bromas)}")
            if hilos_perfil or hilos_pendientes:
                burbuja_lineas.append("• Hilos abiertos:")
                for h in hilos_perfil[:4]:
                    f_str = f" [{h.get('fecha')}]" if h.get("fecha") else ""
                    burbuja_lineas.append(f"   - #{h.get('id')}: {h.get('tema')}{f_str}")
                for hp in hilos_pendientes[:2]:
                    burbuja_lineas.append(f"   - (pendiente): {hp}")

            self.app.cola.put(("hablar_registro", (voz_txt, "\n".join(burbuja_lineas))))
            log("Consulta de lo aprendido mostrada al usuario.")

        threading.Thread(target=_tarea, daemon=True).start()

    def accion_olvidar_aprendizaje(self, tema):
        """Elimina un dato concreto del perfil (tema, palabra, costumbre o hilo)."""
        def _tarea():
            if not tema or not str(tema).strip():
                self.app.cola.put(("hablar", "Dime qué dato, tema o palabra deseas que olvide de tu perfil."))
                return

            t_limpio = str(tema).strip()
            borrado = ad.eliminar_del_perfil(t_limpio)
            try:
                import hilos as m_hilos
                m_hilos.cerrar_pendiente(t_limpio)
            except Exception:
                pass

            if borrado:
                log(f"Dato olvidado del perfil: {t_limpio}")
                self.app.cola.put(("hablar", f"Listo Moisés, olvidé lo que había aprendido sobre «{t_limpio}»."))
            else:
                self.app.cola.put(("hablar", f"No encontré ningún dato guardado sobre «{t_limpio}» en tu perfil."))

        threading.Thread(target=_tarea, daemon=True).start()

    def accion_borrar_perfil(self, arg):
        """Borra todo el perfil y el historial de conversaciones tras confirmación."""
        def _tarea():
            texto = (arg or "").strip().lower()
            if texto in ("confirmar", "confirmar borrar perfil", "si", "sí"):
                ad.reiniciar_perfil_y_conversaciones()
                self.ultima_reflexion = None
                log("Perfil de conversación y registro borrados por completo tras confirmación.")
                self.app.cola.put(("hablar", "He borrado por completo tu perfil de conversación y el registro de charlas."))
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
        "reflexionar_ahora",
        lambda: gestor.accion_reflexionar_ahora(),
        "reflexiona sobre las conversaciones guardadas y actualiza el perfil aprendido sobre Moisés (úsala cuando te pidan 'haz tu reflexión', 'reflexión nocturna', 'dame tu reflexión', 'reflexiona sobre hoy')",
    )
    acciones.registrar(
        "reflexionar_aprendizaje",
        lambda: gestor.accion_reflexionar_ahora(),
        "alias de reflexionar_ahora: ejecuta la reflexión sobre las conversaciones y actualiza el perfil",
    )
    acciones.registrar(
        "que_has_aprendido",
        lambda: gestor.accion_que_has_aprendido(),
        "explica qué has aprendido del estilo, palabras, costumbres e hilos abiertos de Moisés (úsala cuando pregunten 'qué has aprendido de mí', 'qué sabes de mí', 'cuál es mi perfil')",
    )
    acciones.registrar(
        "olvidar_aprendizaje",
        lambda arg: gestor.accion_olvidar_aprendizaje(arg),
        "olvida un dato, tema, costumbre o palabra específica del perfil de Moisés (úsala cuando digan 'olvida lo de...', 'olvida que...'). Lleva texto con el dato a olvidar.",
        con_texto=True,
    )
    acciones.registrar(
        "borrar_perfil",
        lambda arg=None: gestor.accion_borrar_perfil(arg),
        "borra por completo todo el perfil y lo aprendido de Moisés pidiendo confirmación previa (úsala cuando digan 'borra mi perfil', 'olvida todo lo que aprendiste'). Si lleva texto 'confirmar', procede a borrar.",
        con_texto=True,
    )

    log("Módulo de aprendizaje continuo instalado.")
    return gestor
