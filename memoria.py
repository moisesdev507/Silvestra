"""Memoria permanente de hechos, personas, gustos y fechas con filtro de privacidad."""
import datetime
import json
import os
import re
import threading

from config import ARCHIVO_MEMORIA
import acciones
import memoria_busqueda as mb

PALABRAS_PRIVADAS = (
    "clave", "password", "contraseñ", "contrasena", "token", "api_key",
    "apikey", "secret", "cvv", "tarjeta de credito", "pin "
)

_memoria_instancia = None


def limpiar_nombre(texto):
    """Quita frases como 'mi nombre es' y deja solo el nombre."""
    if not texto:
        return texto
    t = texto.strip()
    t = re.sub(
        r"^(hola[,.! ]*)?(me llamo|mi nombre es|yo soy|soy|te llamas|te llamarás|"
        r"tu nombre es|llámame|puedes llamarme)\s+",
        "",
        t,
        flags=re.IGNORECASE,
    )
    return t.strip(" .,!¡¿?")


class Memoria:
    def __init__(self):
        global _memoria_instancia
        _memoria_instancia = self
        self._bloqueo = threading.RLock()
        self.datos = self._vacia()
        self.cargar()

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
            if os.path.exists(ARCHIVO_MEMORIA):
                try:
                    with open(ARCHIVO_MEMORIA, encoding="utf-8") as f:
                        guardado = json.load(f)
                except (OSError, ValueError):
                    guardado = {}
                self.datos.update(guardado)
                self.datos["nombre"] = limpiar_nombre(self.datos.get("nombre"))
                self.datos["creador"] = limpiar_nombre(self.datos.get("creador"))
                if not isinstance(self.datos.get("hechos"), list):
                    self.datos["hechos"] = []
                if not isinstance(self.datos.get("resumenes_tematicos"), dict):
                    self.datos["resumenes_tematicos"] = {}

    def guardar(self):
        with self._bloqueo:
            with open(ARCHIVO_MEMORIA, "w", encoding="utf-8") as f:
                json.dump(self.datos, f, ensure_ascii=False, indent=2)

    def borrar(self):
        with self._bloqueo:
            if os.path.exists(ARCHIVO_MEMORIA):
                os.remove(ARCHIVO_MEMORIA)
            self.datos = self._vacia()

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

    def recordar(self, hecho, fecha=None):
        """Guarda un registro permanente de lo que el dueño cuenta, con fecha."""
        if not hecho:
            return False
        hecho = hecho.strip()
        if not hecho:
            return False

        # Filtro de privacidad estricto
        hecho_low = hecho.lower()
        for p in PALABRAS_PRIVADAS:
            if p in hecho_low:
                print(f"[memoria] Rechazado por filtro de privacidad: '{p}'", flush=True)
                return False

        # Fecha de cuándo se dijo en zona de Panamá
        if not fecha:
            try:
                from zoneinfo import ZoneInfo
                ahora = datetime.datetime.now(ZoneInfo("America/Panama"))
            except Exception:
                ahora = datetime.datetime.now()
            fecha = ahora.strftime("%Y-%m-%d")

        # Prefijo de fecha
        if not re.match(r"^\[\d{4}-\d{2}-\d{2}\]", hecho) and not re.match(r"^\[\d{2}/\d{2}/\d{4}\]", hecho):
            hecho_guardar = f"[{fecha}] {hecho}"
        else:
            hecho_guardar = hecho

        with self._bloqueo:
            # Evitar duplicados exactos
            hecho_puro = re.sub(r"^\[[^\]]+\]\s*", "", hecho).strip().lower()
            for existente in self.datos["hechos"]:
                existente_puro = re.sub(r"^\[[^\]]+\]\s*", "", existente).strip().lower()
                if hecho_puro == existente_puro:
                    return False

            self.datos["hechos"].append(hecho_guardar)

            # Si pasa de ~200 recuerdos, resumir los viejos por tema
            if len(self.datos["hechos"]) > 200:
                mb.resumir_memoria_antigua(self)

            self.guardar()
            total = len(self.datos["hechos"])
            print(f"[memoria] guardados=1 relevantes=0 total={total}", flush=True)
            print(f"[memoria] Nuevo recuerdo permanente guardado: '{hecho_guardar}'", flush=True)
            return True

    def olvidar(self, tema):
        """Borra recuerdos por voz según el tema o palabras clave."""
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
                self.guardar()
                total = len(self.datos["hechos"])
                print(f"[memoria] guardados=0 relevantes=0 total={total}", flush=True)
                print(f"[memoria] Olvidados {len(eliminados)} recuerdos sobre '{tema}'", flush=True)
                return f"Listo. He olvidado lo que sabía sobre '{tema}'."
        return f"No encontré ningún recuerdo guardado sobre '{tema}'."

    def consultar(self, tema=None):
        """Devuelve con total honestidad lo que tiene guardado sobre el dueño o sobre un tema X."""
        creador = self.creador
        t_norm = (tema or "").strip().lower()

        with self._bloqueo:
            hechos = list(self.datos.get("hechos", []))
            resumenes = dict(self.datos.get("resumenes_tematicos", {}))

        total = len(hechos)
        # Consulta general sobre el usuario
        if not t_norm or t_norm in ("mi", "mí", "yo", "sobre mi", "sobre mí", "de mi", "de mí"):
            if not hechos and not resumenes:
                print(f"[memoria] guardados=0 relevantes=0 total={total}", flush=True)
                return f"{creador}, todavía no tengo guardado nada sobre ti. Cuéntame lo que quieras y lo iré recordando."

            elegidos = hechos[-5:]
            limpios = [re.sub(r"^\[[^\]]+\]\s*", "", x).strip() for x in elegidos]
            print(f"[memoria] guardados=0 relevantes={len(limpios)} total={total}", flush=True)
            return f"De ti sé que te llamas {creador}, y recuerdo esto: " + "; ".join(limpios) + "."

        # Consulta sobre tema específico X
        encontrados, n_rel = mb.buscar_recuerdos(hechos, tema, max_recuerdos=5, resumenes_tematicos=resumenes)
        print(f"[memoria] guardados=0 relevantes={n_rel} total={total}", flush=True)
        if not encontrados or n_rel == 0:
            return f"{creador}, no tengo guardado nada sobre '{tema}' todavía."

        limpios = [re.sub(r"^\[[^\]]+\]\s*", "", x).strip() for x in encontrados]
        return f"Sobre {tema} recuerdo: " + "; ".join(limpios) + "."

    def extraer_hechos_conversacion(self, historial, pedir_fn=None):
        """Hilo secundario: usa el proveedor para extraer hechos duraderos del diálogo."""
        try:
            if not historial or len(historial) < 2:
                return

            mensajes_usuario = [m["content"] for m in historial if m.get("role") == "user" and m.get("content")]
            if not mensajes_usuario:
                return

            charla = "\n".join(f"{m.get('role', 'user').upper()}: {m.get('content', '')}" for m in historial[-8:])
            creador = self.creador
            sistema = (
                f"Eres un extractor de memoria objetivo y honesto para Silvestra, asistente de {creador}.\n"
                "Analiza la conversación reciente y extrae TODOS los hechos duraderos que el dueño dijo:\n"
                "- Personas (familiares, amigos, compañeros)\n"
                "- Gustos y preferencias (comida, música, pasatiempos)\n"
                "- Planes, metas y fechas (exámenes, viajes, proyectos)\n"
                "- Trabajo, estudios y opiniones firmes\n\n"
                "REGLAS ESTRICTAS:\n"
                "1. Extrae ÚNICAMENTE lo que el usuario afirmó directamente. Cero suposiciones. Cero salud íntima ni contraseñas.\n"
                "2. Si no hay hechos nuevos o duraderos, responde 'NINGUNO'.\n"
                "3. Formato: una línea por hecho iniciando con 'HECHO: '\n"
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
                        if self.recordar(dato):
                            guardados_ahora += 1

            if guardados_ahora > 0:
                print(f"[memoria] Extracción completada: {guardados_ahora} hechos guardados.", flush=True)
        except Exception as e:
            print(f"[memoria] Error en extracción de conversación: {e}", flush=True)

    def vocabulario(self):
        """Nombres propios que ayudan al oído a no confundirse."""
        palabras = [self.nombre or "", self.creador or ""]
        for h in self.hechos:
            palabras += re.findall(r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+", h)
        vistas = []
        for p in palabras:
            if p and p not in vistas:
                vistas.append(p)
        return ", ".join(vistas[:20])


def instalar(app):
    """Registra las acciones de memoria: olvidar, recuerda_esto y que_sabes."""
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
            ok = mem.recordar(limpio)
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
