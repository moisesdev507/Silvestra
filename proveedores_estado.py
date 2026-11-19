"""Generación del reporte de estado estructurado de proveedores LLM."""
import time
import config


def reporte_estado_proveedores(enfriamientos, pc):
    """Genera el reporte de estado por tarea para voz y burbuja."""
    ahora = time.time()
    prov_map = {}
    for p in config.PROVEEDORES:
        copia = dict(p)
        pc.refrescar_clave_proveedor(copia)
        prov_map[copia["nombre"]] = copia

    estados = {}
    todos = [
        "Groq", "Cloudflare", "Google", "Mistral", "NVIDIA",
        "Cerebras", "OpenRouter", "GitHub", "SambaNova", "Cohere"
    ]
    extras = getattr(config, "PROVEEDORES_EXTRA", [])
    for ext in extras:
        n = ext.get("nombre")
        if n and n not in todos:
            if "Cohere" in todos:
                todos.insert(todos.index("Cohere"), n)
            else:
                todos.append(n)
            prov_map[n] = {
                "nombre": n,
                "base_url": ext.get("url") or ext.get("base_url"),
                "clave": ext.get("clave", ""),
                "modelos": ext.get("modelos", []),
            }

    activos_nombres = []
    enfriando_nombres = []
    sin_clave_nombres = []

    for n in todos:
        p = prov_map.get(n)
        if not p:
            estados[n] = "No configurado"
            sin_clave_nombres.append(n)
            continue
        clave = (p.get("clave") or "").strip()
        if not clave:
            estados[n] = "Sin clave"
            sin_clave_nombres.append(n)
            continue

        t_fin_prov = enfriamientos.get(n, 0)
        prov_modelos = list(p.get("modelos", []))
        modelos_enfriados = []
        for m in prov_modelos:
            t_m = enfriamientos.get(f"{n}::{m}", 0)
            if ahora < t_m:
                modelos_enfriados.append((m, int(t_m - ahora)))

        if ahora < t_fin_prov:
            seg = int(t_fin_prov - ahora)
            estados[n] = f"Enfriamiento ({seg}s restan)"
            enfriando_nombres.append(f"{n} ({seg}s)")
        elif prov_modelos and len(modelos_enfriados) == len(prov_modelos):
            max_seg = max(s for _, s in modelos_enfriados)
            estados[n] = f"Enfriamiento ({max_seg}s restan)"
            enfriando_nombres.append(f"{n} ({max_seg}s)")
        elif modelos_enfriados:
            n_act = len(prov_modelos) - len(modelos_enfriados)
            estados[n] = f"Activo ({n_act}/{len(prov_modelos)} modelos)"
            activos_nombres.append(f"{n} ({n_act} mod)")
            enfriando_nombres.append(f"{n} ({len(modelos_enfriados)} mod en pausa)")
        else:
            estados[n] = "Activo"
            activos_nombres.append(n)

    partes_voz = []
    if activos_nombres:
        partes_voz.append(f"Activos: {', '.join(activos_nombres)}.")
    if enfriando_nombres:
        partes_voz.append(f"En pausa por cuota: {', '.join(enfriando_nombres)}.")
    if sin_clave_nombres:
        partes_voz.append(f"Sin clave: {', '.join(sin_clave_nombres)}.")
    texto_voz = " ".join(partes_voz) if partes_voz else "No hay proveedores configurados."

    lineas = ["🌐 ESTADO DE PROVEEDORES LLM:"]
    for n in todos:
        st = estados.get(n, "Desconocido")
        extra_tag = " [Emergencia]" if n == "Cohere" else ""
        icono = "✅" if "Activo" in st else ("⏳" if "Enfriamiento" in st else "⚪")
        lineas.append(f"{icono} {n}{extra_tag}: {st}")

    lineas.append("\n📋 CADENAS ACTIVAS:")
    for t_nom, t_desc in [
        ("charla", "Charla y órdenes"),
        ("razonamiento", "Razonamiento y código"),
        ("vision", "Visión artificial"),
        ("fondo", "Tareas de fondo"),
    ]:
        cands = [p["nombre"] for p in pc.obtener_candidatos_tarea(t_nom, enfriamientos)]
        ruta = " ➔ ".join(cands) if cands else "Ninguno disponible"
        lineas.append(f"• {t_desc}: {ruta}")

    lineas.append("• Voz a texto: Groq (Whisper) con respaldo local Vosk")
    lineas.append("• Respaldo de emergencia: Cohere (Trial 1,000 llamadas/mes)")
    lineas.append("• Respaldo local sin red: Activo (frase natural y reintento en segundo plano)")

    texto_burbuja = "\n".join(lineas)
    return texto_voz, texto_burbuja
