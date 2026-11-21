"""Memoria permanente de hechos, personas, gustos y fechas con filtro de privacidad."""
import os
import re
import threading

from config import ARCHIVO_MEMORIA
import acciones
import memoria_busqueda as mb
import memoria_tiempo as mt
import persistencia_segura as ps
from memoria_almacen import AlmacenMemoriaCognitiva
from memoria_gestor import GestorMemoria
from memoria_migrador import migrar_legado_a_sqlite
from memoria_modelos import limpiar_nombre, validar_usuario_id

_memoria_instancia = None


class Memoria:
    def __init__(self, ruta_db=None, ruta_json=None, usuario_id="local"):
        global _memoria_instancia
        _memoria_instancia = self
        self._bloqueo = threading.RLock()
        self.bloqueo_invitado = False
        self.usuario_id = validar_usuario_id(usuario_id)
        self.ruta_json = os.fspath(ruta_json or ARCHIVO_MEMORIA) if self.usuario_id == "local" or ruta_json else None
        ruta_db = ruta_db or os.environ.get("SILVESTRA_MEMORIA_DB")
        if ruta_db is None:
            ruta_db = os.path.join(os.path.dirname(os.path.abspath(self.ruta_json or ARCHIVO_MEMORIA)), "silvestra_memoria.db")
        self.almacen = AlmacenMemoriaCognitiva(ruta_db, self.usuario_id)
        self.gestor = GestorMemoria(self.almacen, self.usuario_id)
        self.datos = self._vacia()
        self.cargar()
        if self.ruta_json:
            migrar_legado_a_sqlite(self.almacen, os.path.dirname(os.path.abspath(self.ruta_json)), self.usuario_id)

    @staticmethod
    def _vacia():
        return {
            "nombre": None,
            "creador": None,
            "proposito": None,
            "hechos": [],
            "resumenes_tematicos": {},
        }

    def cargar(self):
        with self._bloqueo:
            if not self.ruta_json:
                self.datos["hechos"] = [r["contenido"] for r in self.almacen.listar_recuerdos(10000)]
                return
            guardado = ps.cargar_json_seguro(self.ruta_json, {})
            if isinstance(guardado, dict):
                self.datos.update(guardado)
            self.datos["nombre"] = limpiar_nombre(self.datos.get("nombre"))
            self.datos["creador"] = limpiar_nombre(self.datos.get("creador"))
            if not isinstance(self.datos.get("hechos"), list):
                self.datos["hechos"] = []
            if not isinstance(self.datos.get("resumenes_tematicos"), dict):
                self.datos["resumenes_tematicos"] = {}

    def guardar(self):
        with self._bloqueo:
            return ps.guardar_json_atomico(self.ruta_json, self.datos) if self.ruta_json else True

    def borrar(self):
        with self._bloqueo:
            for r in self.almacen.listar_recuerdos(10000, solo_activos=False):
                self.almacen.eliminar_recuerdo(r["id"])
            if self.ruta_json and os.path.exists(self.ruta_json):
                os.remove(self.ruta_json)
            self.datos = self._vacia()

    def cerrar(self):
        self.almacen.cerrar()

    def __del__(self):
        try:
            self.cerrar()
        except Exception:
            pass

    @property
    def nombre(self):
        return self.datos.get("nombre")

    @property
    def creador(self):
        return self.datos.get("creador") or "Moisés"

    @property
    def proposito(self):
        return self.datos.get("proposito")

    @property
    def hechos(self):
        return self.datos["hechos"]

    def nacer(self, nombre, creador, proposito):
        with self._bloqueo:
            self.datos["nombre"] = limpiar_nombre(nombre)
            self.datos["creador"] = limpiar_nombre(creador) or "Moisés"
            self.datos["proposito"] = (proposito or "ayudarte en lo que necesites").strip()
            self.guardar()

    def recordar(self, hecho, fecha=None, origen="explicito", texto_usuario="",
                 fuente="conversacion", canal="texto", contexto=None):
        if getattr(self, "bloqueo_invitado", False):
            return False
        hecho = mt.anclar_fechas_relativas(str(hecho or "").strip())
        if fecha and not re.match(r"^\[\d{4}-\d{2}-\d{2}\]", str(hecho or "")):
            hecho = f"[{fecha}] {hecho}"
        from memoria_adaptadores import procesar_candidato
        resultado = procesar_candidato(self, hecho, texto_usuario, fuente, canal,
                                       contexto, origen == "explicito")
        return bool(resultado.get("aceptado"))

    def olvidar(self, tema):
        if not tema or not tema.strip():
            return "No me dijiste qué recuerdo quieres que olvide."
        t_limpio = tema.strip().lower()
        palabras = set(re.findall(r"\b[a-zA-ZáéíóúÁÉÍÓÚñÑ]{3,}\b", t_limpio))

        with self._bloqueo:
            eliminados = []
            nuevos_hechos = []
            for h in self.datos.get("hechos", []):
                h_texto = h.lower()
                h_palabras = set(re.findall(r"\b[a-zA-ZáéíóúÁÉÍÓÚñÑ]{3,}\b", h_texto))
                if t_limpio in h_texto or (palabras and len(palabras & h_palabras) >= min(len(palabras), 2)):
                    eliminados.append(h)
                else:
                    nuevos_hechos.append(h)

            if eliminados:
                self.datos["hechos"] = nuevos_hechos
                self.gestor.olvidar(tema)
                self.guardar()
                total = len(self.datos["hechos"])
                print(f"[memoria] guardados=0 relevantes=0 total={total}", flush=True)
                print(f"[memoria] olvidados={len(eliminados)}", flush=True)
                return f"Listo. He olvidado lo que sabía sobre '{tema}'."
        return f"No encontré ningún recuerdo guardado sobre '{tema}'."

    def recuperar(self, consulta, contexto="", limite=5):
        """Devuelve resultados trazables e incertidumbre sin filtrar otros perfiles."""
        from memoria_recuperacion import recuperar
        return recuperar(self.gestor, consulta, self.usuario_id, contexto, limite)

    def consultar_relacional(self, consulta, contexto="", max_profundidad=2, max_resultados=20):
        from memoria_relaciones import consultar_relacional
        return consultar_relacional(self.gestor.grafo, consulta, self.usuario_id,
                                    contexto, max_profundidad, max_resultados)

    def consultar(self, tema=None):
        creador = self.creador
        t_norm = (tema or "").strip().lower()

        with self._bloqueo:
            hechos = list(self.datos.get("hechos", []))
            resumenes = dict(self.datos.get("resumenes_tematicos", {}))

        total = len(hechos)
        if not t_norm or t_norm in ("mi", "mí", "yo", "sobre mi", "sobre mí", "de mi", "de mí"):
            if not hechos and not resumenes:
                print(f"[memoria] guardados=0 relevantes=0 total={total}", flush=True)
                return f"{creador}, todavía no tengo guardado nada sobre ti. Cuéntame lo que quieras y lo iré recordando."

            elegidos = hechos[-5:]
            limpios = [re.sub(r"^\[[^\]]+\]\s*", "", x).strip() for x in elegidos]
            print(f"[memoria] guardados=0 relevantes={len(limpios)} total={total}", flush=True)
            return f"De ti sé que te llamas {creador}, y recuerdo esto: " + "; ".join(limpios) + "."

        paquete = self.recuperar(tema, limite=5)
        encontrados = [r["contenido"] for r in paquete["resultados"]]
        print(f"[memoria] guardados=0 relevantes={len(encontrados)} total={total}", flush=True)
        if not encontrados:
            return f"{creador}, no tengo guardado nada sobre '{tema}' todavía."

        limpios = [re.sub(r"^\[[^\]]+\]\s*", "", x).strip() for x in encontrados]
        return f"Sobre {tema} recuerdo: " + "; ".join(limpios) + "."

    def extraer_hechos_conversacion(self, historial, pedir_fn=None):
        try:
            if getattr(self, "bloqueo_invitado", False):
                return
            from memoria_adaptadores import historial_prohibido, procesar_extraccion
            if historial_prohibido(historial):
                return
            if not historial or len(historial) < 2:
                return

            mensajes_usuario = [m["content"] for m in historial if m.get("role") == "user" and m.get("content")]
            if not mensajes_usuario:
                return

            charla = "\n".join(f"{m.get('role', 'user').upper()}: {m.get('content', '')}" for m in historial[-8:])
            creador = self.creador
            sistema = (
                f"Eres un extractor de memoria objetivo y honesto para Silvestra, asistente de {creador}.\n"
                "Analiza la conversación reciente y extrae hechos duraderos que el dueño dijo:\n"
                "- Personas (familiares, amigos, compañeros)\n"
                "- Gustos y preferencias (comida, música, pasatiempos)\n"
                "- Planes, metas y fechas (exámenes, viajes, proyectos reales)\n"
                "- Trabajo, estudios y opiniones firmes\n\n"
                "REGLAS ESTRICTAS:\n"
                "1. Extrae ÚNICAMENTE lo que el usuario afirmó directamente sobre su vida real o proyectos personales. Cero suposiciones. Cero salud íntima ni contraseñas.\n"
                "2. PROHIBIDO guardar recuerdos sobre comandos, pruebas, pedidos a Silvestra, HUD, casa inteligente, hora, clima, saludos ni interacciones con la asistente.\n"
                "3. PROHIBIDO especular o usar frases como 'el usuario parece tener interés en...'. Cada hecho debe ser concreto, útil y en UNA sola línea.\n"
                "4. Si no hay hechos personales nuevos o relevantes, responde 'NINGUNO'.\n"
                "5. Formato: una línea por hecho iniciando con 'HECHO: '\n"
                "Ejemplo:\n"
                "HECHO: A Moisés le gusta la comida italiana.\n"
                "HECHO: Su hermano Carlos vive en David."
            )
            mensajes = [
                {"role": "system", "content": sistema},
                {"role": "user", "content": f"Conversación reciente:\n{charla}"},
            ]

            if pedir_fn:
                crudo = pedir_fn(mensajes, tarea="fondo")
            else:
                import proveedores
                crudo = proveedores.completar(mensajes, tarea="fondo")

            if not crudo or "ninguno" in crudo.lower():
                return

            guardados_ahora = 0
            for linea in crudo.splitlines():
                s = linea.strip()
                if re.match(r"^HECHO\s*:\s*", s, re.I):
                    dato = re.sub(r"^HECHO\s*:\s*", "", s, flags=re.I).strip(" *\"'")
                    if dato and dato.lower() not in ("ninguno", "ninguna", "nada"):
                        if procesar_extraccion(self, dato, historial).get("aceptado"):
                            guardados_ahora += 1

            if guardados_ahora > 0:
                print(f"[memoria] Extracción completada: {guardados_ahora} hechos guardados.", flush=True)
        except Exception as e:
            print(f"[memoria] Error en extracción ({type(e).__name__})", flush=True)

    def vocabulario(self):
        palabras = [self.nombre or "", self.creador or ""]
        for h in self.hechos:
            palabras += re.findall(r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+", h)
        vistas = []
        for p in palabras:
            if p and p not in vistas:
                vistas.append(p)
        return ", ".join(vistas[:20])


def instalar(app):
    def _accion_olvidar(arg=None):
        mem = getattr(app, "memoria", None) or _memoria_instancia
        res = mem.olvidar(arg) if mem else "No pude acceder a la memoria."
        if hasattr(app, "cola") and app.cola:
            app.cola.put(("hablar", res))
        return res

    def _accion_recordar_esto(arg=None):
        mem = getattr(app, "memoria", None) or _memoria_instancia
        if not arg or not str(arg).strip():
            arg = getattr(app, "ultimo_texto_usuario", "") or getattr(
                getattr(app, "cerebro", None), "ultimo_texto_usuario", ""
            )
        limpio = re.sub(
            r"^(?:recuerda\s+(?:esto|que)?|anota\s+que|guarda\s+que|apunta\s+que)[:\s]*",
            "",
            str(arg).strip(),
            flags=re.I,
        ).strip()
        if not limpio:
            res = "No me dijiste qué dato quieres que recuerde."
        elif mem:
            ok = mem.recordar(limpio, origen="explicito", texto_usuario=str(arg), fuente="orden_explicita")
            creador = mem.creador
            res = f"Listo, {creador}. Guardé en mi memoria: {limpio}" if ok else f"Ya tenía guardado ese dato, {creador}."
        else:
            res = "No pude acceder a la memoria."

        if hasattr(app, "cola") and app.cola:
            app.cola.put(("hablar", res))
        return res

    def _accion_consultar(arg=None):
        mem = getattr(app, "memoria", None) or _memoria_instancia
        res = mem.consultar(arg) if mem else "No pude acceder a la memoria."
        if hasattr(app, "cola") and app.cola:
            app.cola.put(("hablar", res))
        return res

    acciones.registrar(
        "olvidar",
        _accion_olvidar,
        "olvida o borra un recuerdo de la memoria sobre un tema o dato. Escribe: ACCION: olvidar | tema a olvidar",
        con_texto=True,
    )
    acciones.registrar(
        "guardar_recuerdo",
        _accion_recordar_esto,
        "guarda de inmediato un hecho en la memoria cuando el dueño diga 'recuerda esto', 'recuerda que', 'anota que'. Escribe: ACCION: guardar_recuerdo | dato",
        con_texto=True,
    )
    acciones.registrar(
        "recuerda_esto",
        _accion_recordar_esto,
        "alias de guardar_recuerdo: guarda un hecho en la memoria. Escribe: ACCION: recuerda_esto | dato",
        con_texto=True,
    )
    acciones.registrar(
        "consultar_memoria",
        _accion_consultar,
        "informa con honestidad lo que Silvestra sabe sobre el dueño o sobre un tema X ('qué sabes de mí', 'qué sabes de mi trabajo', 'qué sabes de X'). Escribe: ACCION: consultar_memoria | tema (o 'mí')",
        con_texto=True,
    )
    acciones.registrar(
        "que_sabes",
        _accion_consultar,
        "alias de consultar_memoria: informa qué sabe sobre el dueño o sobre un tema X. Escribe: ACCION: que_sabes | tema",
        con_texto=True,
    )
