"""Generación y redacción de prompts para Antigravity basados en autopropuestas.

Lee el stack, módulos reales de arquitectura de PROYECTO.md, evalúa riesgos de
seguridad y privacidad, y redacta un prompt conciso, técnico y directo (cuerpo máx ~350 palabras)
listo para ejecutar en Antigravity, adjuntando siempre al final un bloque fijo de reglas.
"""
import os
import re
import proveedores

RUTA_PROYECTO_MD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "PROYECTO.md")
CARPETA_PROPUESTAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "propuestas")

PATRONES_RIESGO = [
    (r"\b(borrar|eliminar|remover|destruir|rm|unlink)\b", "Implica borrado o eliminación de archivos o datos."),
    (r"\b(ejecutar comandos?|consola|powershell|cmd|terminal|shell|subprocess)\b", "Implica ejecución de comandos del sistema operativo."),
    (r"\b(abrir puerto|servidor|socket|escuchar en puerto)\b", "Implica abrir puertos de red o exponer servicios locales."),
    (r"\b(cuentas? externas?|credenciales|contraseñas?|login|iniciar sesion)\b", "Implica manejo o acceso a cuentas o credenciales externas."),
    (r"\b(subir datos fuera|enviar a la nube|exportar datos fuera)\b", "Implica transferencia de datos hacia servicios externos no previstos."),
    (r"\b(cámara oculta|grabar pantalla continuo|espíar|vigilar)\b", "Toca aspectos sensibles de privacidad del usuario."),
]

BLOQUE_REGLAS_OBLIGATORIAS = (
    "Reglas obligatorias:\n"
    "- Solo servicios gratuitos.\n"
    "- No romper lo que funciona.\n"
    "- No escribir claves en el código.\n"
    "- Archivos de máximo ~10 KB.\n"
    "- Nada de Qt desde hilos secundarios (los hilos solo usan app.cola.put), y nada de red ni trabajo pesado en el hilo principal.\n"
    "- Español de Panamá en todo lo que ella diga.\n"
    "- main.py casi sin cambios.\n"
    "- Actualizar PROYECTO.md."
)


def obtener_archivos_proyecto():
    """Devuelve la lista real de archivos .py existentes en la raíz del proyecto."""
    raiz = os.path.dirname(os.path.abspath(__file__))
    try:
        return sorted([f for f in os.listdir(raiz) if f.endswith(".py")])
    except Exception:
        return []


def obtener_resumen_arquitectura():
    """Extrae una línea por módulo de la sección de arquitectura de PROYECTO.md."""
    lineas_resumen = []
    if os.path.exists(RUTA_PROYECTO_MD):
        try:
            with open(RUTA_PROYECTO_MD, "r", encoding="utf-8") as f:
                contenido = f.read()
            m = re.search(r"## Arquitectura \(archivos\)\s*\n(.*?)(?=\n## |\Z)", contenido, re.DOTALL)
            if m:
                for linea in m.group(1).strip().splitlines():
                    linea = linea.strip()
                    if not linea.startswith("- "):
                        continue
                    if "hilos.py" in linea:
                        lineas_resumen.append("- `hilos.py`: memoria de temas abiertos, NO manejo de hilos de ejecución.")
                        continue
                    partes = linea.split(":", 1)
                    if len(partes) == 2:
                        mod = partes[0].strip()
                        desc = partes[1].strip()
                        oracion = desc.split(". ")[0].strip()
                        if not oracion.endswith("."):
                            oracion += "."
                        lineas_resumen.append(f"{mod}: {oracion}")
                    else:
                        lineas_resumen.append(linea)
        except Exception:
            pass

    if not lineas_resumen:
        lineas_resumen = [
            "- `main.py`: ciclo principal, inicialización de módulos y Qt.",
            "- `hilos.py`: memoria de temas abiertos, NO manejo de hilos de ejecución.",
            "- `acciones.py`: registro central de acciones con registrar().",
            "- `cerebro.py`: armado de prompt e interacción con LLM.",
            "- `proveedores.py`: cadena multillm con respaldo.",
        ]
    return "\n".join(lineas_resumen)


def sanitizar_prompt(texto):
    """Limpia secretos del prompt sin ocultar config.py ni romper rutas."""
    if not texto:
        return ""
    s = str(texto)
    s = re.sub(r"gsk_[A-Za-z0-9_-]{20,}", "[CLAVE_PROTEGIDA]", s)
    s = re.sub(r"sk-or-v1-[A-Za-z0-9_-]{20,}", "[CLAVE_PROTEGIDA]", s)
    s = re.sub(r"sk-[A-Za-z0-9_-]{20,}", "[CLAVE_PROTEGIDA]", s)
    s = re.sub(r"AQ\.[A-Za-z0-9_-]{20,}", "[CLAVE_PROTEGIDA]", s)
    s = re.sub(r"\d{8,12}:[A-Za-z0-9_-]{25,50}", "[TOKEN_PROTEGIDO]", s)
    s = re.sub(r"\[configuraci[oó]n\]", "config.py", s, flags=re.I)
    s = re.sub(r"\[RUTA_LOCAL\]", "", s)
    s = re.sub(r"\s*\([~≈]\s*\d+\s*KB\)", "", s, flags=re.I)
    return s.strip()


def evaluar_riesgo(descripcion, motivo=""):
    """Detecta si una propuesta implica permisos elevados o riesgos de privacidad."""
    texto_eval = f"{descripcion} {motivo}".lower()
    motivos_riesgo = []
    for patron, exp in PATRONES_RIESGO:
        if re.search(patron, texto_eval):
            motivos_riesgo.append(exp)

    if motivos_riesgo:
        return True, " ".join(motivos_riesgo)
    return False, ""


def redactar_prompt(app, propuesta):
    """Redacta el prompt para Antigravity: cuerpo máx ~350 palabras y bloque fijo de reglas al final."""
    desc = propuesta.get("descripcion", "")
    motivo = propuesta.get("motivo", "")
    id_prop = propuesta.get("id", "prop_1")

    es_riesgoso, detalle_riesgo = evaluar_riesgo(desc, motivo)
    if not propuesta.get("riesgo") and es_riesgoso:
        propuesta["riesgo"] = True
        propuesta["detalle_riesgo"] = detalle_riesgo

    resumen_arquitectura = obtener_resumen_arquitectura()

    sistema = (
        "Eres Silvestra, una asistente de IA de escritorio para Windows desarrollada en Python 3.12 y PySide6.\n"
        "Tu creador es Moisés, un estudiante de Panamá que te programa con Antigravity en VS Code.\n"
        "Tu tarea es redactar el cuerpo de un prompt técnico, directo y listo para pegar en Antigravity.\n\n"
        "REGLAS ESTRICTAS DE REDACCIÓN DEL CUERPO:\n"
        "1. LONGITUD: Máximo ~350 palabras para el cuerpo que redactas. Sin preámbulos, saludos ni rellenos.\n"
        "2. ESTRUCTURA:\n"
        "   - Línea 1 obligatoria: 'Lee PROYECTO.md. <Título y objetivo conciso en una frase>'\n"
        "   - Tarea 1 obligatoria: '1. Antes de escribir código, propón la solución más simple que cumpla el objetivo y dime si hay alternativas más baratas o seguras; espera mi confirmación si cambia mucho el plan.'\n"
        "   - Siguientes tareas numeradas concretas nombrando archivos reales existentes o nuevo módulo de máx ~10 KB con su función instalar(app) y acciones.registrar(...).\n"
        "   - Sección 'Cómo probarlo' con comandos de Windows (.venv\\Scripts\\python.exe main.py, .venv\\Scripts\\pip.exe install ... y revisar silvestra.log).\n"
        "3. REGLAS SOBRE RIESGO Y REGLAS FIJAS:\n"
        "   - NO incluyas ninguna sección de 'Reglas obligatorias'; el sistema la agregará textualmente al final por código.\n"
        "   - NUNCA uses la palabra 'RIESGO' ni etiquetas '⚠️ RIESGO' para recomendaciones o notas técnicas (como hilos secundarios, timeouts, puertos locales o librerías). 'RIESGO' es EXCLUSIVO para peligros reales de seguridad o privacidad (ej. borrar archivos, exponer contraseñas, cámara oculta). Si no hay riesgo de seguridad o privacidad, NO uses la palabra RIESGO.\n"
        "   - Si se indica riesgo de seguridad/privacidad real: incluye '⚠️ RIESGO DE SEGURIDAD/PRIVACIDAD: <detalle>'. Si no hay riesgo, omítelo por completo.\n"
        "4. PRECISIÓN Y CONVENCIONES:\n"
        "   - Stack: Windows, Python 3.12, PySide6, entorno .venv.\n"
        f"   - Módulos reales de la arquitectura (PROYECTO.md):\n{resumen_arquitectura}\n"
        "   - NUNCA confundas hilos.py (es memoria de temas abiertos, NO hilos de ejecución).\n"
        "   - Integración: cada módulo nuevo trae su instalar(app) y registra sus acciones con acciones.registrar(...); en main.py solo se agrega una línea de instalar. No se edita un diccionario central.\n"
        "   - NUNCA propongas servicios públicos o abiertos (como brokers de prueba públicos tipo test.mosquitto.org); solo servicios locales o con clave propia. Si un dispositivo tiene opción local más simple (ej. foco WiZ por red local), menciónala como primera alternativa.\n"
        "   - NUNCA uses marcadores genéricos como '[configuración]'; di 'config.py'.\n"
        "   - NUNCA estimes tamaños en KB por archivo; si mencionas el módulo di solo 'máx ~10 KB'.\n"
        "   - Si falta algún dato técnico externo, márcalo explícitamente en una sola línea como: 'dato por confirmar: <parámetro faltante>'."
    )

    consulta = (
        f"Propuesta a redactar:\n"
        f"ID: {id_prop}\n"
        f"Descripción: {desc}\n"
        f"Motivo: {motivo}\n"
        f"Riesgo de seguridad/privacidad: {'SÍ: ' + detalle_riesgo if es_riesgoso else 'Ninguno (NO usar etiqueta de riesgo)'}\n\n"
        "Redacta únicamente el cuerpo del prompt (máx ~350 palabras) sin incluir la sección de reglas obligatorias."
    )

    cuerpo_generado = None
    try:
        mensajes = [{"role": "system", "content": sistema}, {"role": "user", "content": consulta}]
        cuerpo_generado = proveedores.completar(mensajes, timeout=25)
    except Exception as e:
        print(f"[propuestas_prompt] Fallo en proveedores para redactar prompt: {e}", flush=True)

    if not cuerpo_generado or len(cuerpo_generado) < 80:
        seccion_riesgo = f"\n⚠️ RIESGO DE SEGURIDAD/PRIVACIDAD: {detalle_riesgo}\n" if es_riesgoso else ""
        cuerpo_generado = (
            f"Lee PROYECTO.md. {desc}:\n\n"
            f"1. Antes de escribir código, propón la solución más simple que cumpla el objetivo y dime si hay alternativas más baratas o seguras; espera mi confirmación si cambia mucho el plan.\n"
            f"2. Diseña e implementa la solución en un módulo nuevo (máx ~10 KB) con su propia función instalar(app), registrando las acciones con acciones.registrar(...). En main.py solo agrega la línea de instalar(self).\n"
            f"3. Si requiere configuración externa o credenciales, agrégalas en config.py (dato por confirmar: parámetros de conexión). NUNCA uses brokers o servicios públicos; usa un broker local con autenticación o la alternativa local más simple (ej. bombillo WiZ por red local).\n"
            f"{seccion_riesgo}\n"
            f"Cómo probarlo:\n"
            f"- Instalar dependencias: .venv\\Scripts\\pip.exe install ...\n"
            f"- Iniciar: .venv\\Scripts\\python.exe main.py\n"
            f"- Revisar que no haya excepciones en silvestra.log."
        )

    cuerpo_limpio = sanitizar_prompt(cuerpo_generado)

    # Si el modelo incluyó un bloque de Reglas obligatorias por su cuenta, removerlo para evitar duplicados
    cuerpo_limpio = re.sub(r"(?i)\n+Reglas obligatorias:.*?(?=\n\n[A-Z]|\Z)", "", cuerpo_limpio, flags=re.DOTALL).strip()

    # Agregar SIEMPRE textualmente el bloque fijo al final del prompt
    prompt_completo = f"{cuerpo_limpio}\n\n{BLOQUE_REGLAS_OBLIGATORIAS}"

    os.makedirs(CARPETA_PROPUESTAS, exist_ok=True)
    ruta_guardado = os.path.join(CARPETA_PROPUESTAS, f"prompt_{id_prop}.md")
    try:
        with open(ruta_guardado, "w", encoding="utf-8") as f:
            f.write(prompt_completo)
        print(f"[propuestas_prompt] Prompt guardado en: {ruta_guardado}", flush=True)
    except Exception as e:
        print(f"[propuestas_prompt] Error guardando prompt: {e}", flush=True)

    return prompt_completo
