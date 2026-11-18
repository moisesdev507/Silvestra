import json
import os
import re

from config import ARCHIVO_MEMORIA

MAX_HECHOS = 40


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

    # Atajos de lectura
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

    def recordar(self, hecho):
        hecho = hecho.strip()
        if not hecho or hecho in self.datos["hechos"]:
            return
        self.datos["hechos"].append(hecho)
        self.datos["hechos"] = self.datos["hechos"][-MAX_HECHOS:]
        self.guardar()

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