"""Ideas para mejorar: Silvestra anota lo que le piden y todavía no sabe hacer."""
import difflib
import json
import os
import time

import acciones

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ideas.json")


def cargar():
    try:
        with open(RUTA, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def anotar(texto):
    texto = (texto or "").strip()
    if not texto:
        return
    datos = cargar()
    for d in datos:
        if difflib.SequenceMatcher(None, d["texto"].lower(), texto.lower()).ratio() > 0.7:
            d["veces"] += 1
            break
    else:
        datos.append({"texto": texto, "veces": 1, "fecha": time.strftime("%Y-%m-%d")})
    try:
        with open(RUTA, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    try:
        import propuestas
        propuestas.notificar_idea_para_propuesta(texto)
    except Exception:
        pass


def resumen(maximo=8):
    datos = sorted(cargar(), key=lambda d: -d.get("veces", 1))[:maximo]
    if not datos:
        return "ninguna todavía"
    return "; ".join(f"{d['texto']} (pedida {d.get('veces', 1)} veces)" for d in datos)


def instalar(app):
    acciones.registrar(
        "anotar_idea",
        anotar,
        "anota una idea de mejora cuando te piden algo que todavía no sabes hacer. "
        "Escribe: ACCION: anotar_idea | lo que te pidieron, en pocas palabras",
        con_texto=True,
    )