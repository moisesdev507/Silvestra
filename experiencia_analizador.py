"""Análisis conservador de experiencias: evidencia y lectura permanecen separadas."""
import re
import memoria_filtro


def analizar(datos):
    esperado = str(datos.get("resultado_esperado") or "").strip()
    observado = str(datos.get("resultado_observado") or "").strip()
    if len(observado) < 8 or observado.casefold() in {"ok", "hecho", "listo", "sin cambios"}:
        return {"util": False, "motivo": "trivial"}
    textos = [esperado, observado, *datos.get("factores", ()), *datos.get("condiciones", ())]
    if any(memoria_filtro._contiene_secreto(str(x)) for x in textos):
        return {"util": False, "motivo": "privacidad"}
    verificada = bool(datos.get("verificada"))
    exito = datos.get("exito")
    if exito is None and verificada and esperado:
        exito = re.sub(r"\W+", " ", esperado.casefold()) == re.sub(r"\W+", " ", observado.casefold())
    categoria = str(datos.get("categoria") or "general").casefold()[:100]
    factores = tuple(str(x)[:200] for x in datos.get("factores", ()) if str(x).strip())
    condiciones = tuple(str(x)[:200] for x in datos.get("condiciones", ()) if str(x).strip())
    clave = re.sub(r"\W+", "_", categoria + "_" + "_".join(factores[:2]).casefold()).strip("_")[:140] or "general"
    interpretacion = ("Éxito comprobado bajo estas condiciones." if exito is True else
        "Resultado adverso verificado; revisar condiciones antes de repetir." if exito is False else
        "Resultado observado sin verificación suficiente; requiere evidencia independiente.")
    return {"util": True, "exito": exito, "verificada": verificada, "categoria": categoria,
        "clave_patron": clave, "factores": factores, "condiciones": condiciones,
        "interpretacion": interpretacion, "esperado": esperado, "observado": observado}
