"""Memoria permanente de hechos, personas, gustos y fechas con filtro de privacidad."""
import datetime
import json
import os
import re

from config import ARCHIVO_MEMORIA
import acciones

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
        self.datos = self._vacia()
        self.cargar()

    @staticmethod
    def _vacia():
        return {"nombre": None, "creador": None, "proposito": None, "hechos": []}

    def cargar(self):
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

    def guardar(self):
        with open(ARCHIVO_MEMORIA, "w", encoding="utf-8") as f:
            json.dump(self.datos, f, ensure_ascii=False, indent=2)

    def borrar(self):
        if os.path.exists(ARCHIVO_MEMORIA):
            os.remove(ARCHIVO_MEMORIA)
        self.datos = self._vacia()

    @property
    def nombre(self):
        return self.datos.get("nombre")

    @property
    def creador(self):
        return self.datos.get("creador")

    @property
    def proposito(self):
        return self.datos.get("proposito")

    @property
    def hechos(self):
        return self.datos["hechos"]

    def nacer(self, nombre, creador, proposito):
        self.datos["nombre"] = limpiar_nombre(nombre)
        self.datos["creador"] = limpiar_nombre(creador) or "mi creador"
        self.datos["proposito"] = (proposito or "ayudarte en lo que necesites").strip()
        self.guardar()

    def recordar(self, hecho, fecha=None):
        """Guarda un registro permanente de lo que el dueño cuenta, con fecha."""
        if not hecho:
            return
        hecho = hecho.strip()
        if not hecho:
            return

        # Filtro de privacidad estricto
        hecho_low = hecho.lower()
        for p in PALABRAS_PRIVADAS:
            if p in hecho_low:
                print(f"[memoria] Rechazado por filtro de privacidad: '{p}'", flush=True)
                return

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

        # Evitar duplicados exactos
        hecho_puro = re.sub(r"^\[[^\]]+\]\s*", "", hecho).strip().lower()
        for existente in self.datos["hechos"]:
            existente_puro = re.sub(r"^\[[^\]]+\]\s*", "", existente).strip().lower()
            if hecho_puro == existente_puro:
                return

        self.datos["hechos"].append(hecho_guardar)
        self.guardar()
        print(f"[memoria] Nuevo recuerdo permanente guardado: '{hecho_guardar}'", flush=True)

    def olvidar(self, tema):
        """Borra un recuerdo por voz según el tema o palabras clave."""
        if not tema or not tema.strip():
            return "No me dijiste qué recuerdo quieres que olvide."
        t_limpio = tema.strip().lower()
        palabras = set(re.findall(r"\b[a-zA-ZáéíóúÁÉÍÓÚñÑ]{3,}\b", t_limpio))
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
            print(f"[memoria] Olvidados {len(eliminados)} recuerdos sobre '{tema}'", flush=True)
            return f"Listo. He olvidado lo que sabía sobre '{tema}'."
        return f"No encontré ningún recuerdo guardado sobre '{tema}'."

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
    """Registra la acción 'olvidar' para borrar recuerdos por voz."""
    def _accion_olvidar(arg=None):
        mem = getattr(app, "memoria", None) or _memoria_instancia
        res = mem.olvidar(arg) if mem else "No pude acceder a la memoria."
        if hasattr(app, "cola") and app.cola:
            app.cola.put(("hablar", res))
        return res

    acciones.registrar(
        "olvidar",
        _accion_olvidar,
        "olvida o borra un recuerdo de la memoria sobre un tema o dato. Escribe: ACCION: olvidar | tema a olvidar",
        con_texto=True,
    )
