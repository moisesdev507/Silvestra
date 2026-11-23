"""Acciones de consulta y borrado del perfil de aprendizaje.

Mixin extraído de aprendizaje.py para cumplir el límite de 15 KB por archivo.
La fachada `aprendizaje.py` mantiene el ciclo de reflexión y el registro de acciones.
"""
import threading

import aprendizaje_datos as ad

log = ad.log


class AccionesPerfilMixin:
    """Acciones del usuario sobre el perfil aprendido (hilo secundario → app.cola)."""

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
