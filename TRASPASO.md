# TRASPASO — LYRIS // SILVESTRA

## Arquitectura y reglas
Asistente personal modular Python/Windows con avatar PySide6, voz/escucha, percepción y Context Engine, memoria cognitiva, planificación, permisos y ejecución supervisada. La UI solo se toca desde Qt; hilos secundarios comunican por `app.cola`/señales. Límite: <= 15,360 B por `.py`; <= 6,656 B aquí. Las inferencias no son hechos ni autorizan acciones. Operaciones sensibles requieren confirmación.

## Componentes
- `main.py`, `eventos.py`, `cara_*.py`: aplicación Qt, avatar holográfico y cola de eventos.
- `voz*.py`, `oido*.py`, `audio_*.py`: TTS, reproducción/RMS, captura y VAD.
- `cerebro*.py`, `respuesta_flujo.py`, `proveedores*.py`: conversación, prompt e identidad Lyris.
- `cerebro_grafo.py`, `cerebro_planificador.py`, `cerebro_entrenamiento.py`: grafo de conocimiento, multi-paso y auto-aprendizaje.
- `cerebro_trabajo.py`, `cerebro_proactivo.py`: memoria de trabajo corta, resolución anafórica y proactividad situacional.
- `memoria*.py`, `persistencia_segura.py`: memoria SQLite/FTS5, linaje y consolidación.
- `contexto_*.py`, `multimodal_*.py`: contexto Windows y percepción pasiva.
- `razonamiento_*.py`, `planificacion_*.py`: planes y aprendizaje trazable.
- `ejecucion_*.py`, `permisos_*.py`, `acciones.py`: ejecución validada y permisos por niveles.
- `iniciativa*.py`, `recordatorios.py`, `telegram_*.py`: iniciativa cancelable y puente Telegram.
- `pantalla_remota*.py`, `ecosistema_*.py`: HUD web Galaxy Tab A7, SSE, tema esfera y auto-enlace LAN.
- `habilidades_archivos.py`, `aprendiz_habilidades.py`: archivos seguros y auto-aprendizaje con auditoría AST.

## Fases cerradas
- Fase 1 a Fase 5: núcleo cognitivo, percepción, permisos supervisados, memoria y aprendizaje validados.
- Fase 6 (Etapas 1 y 2): contratos sanitizados, puente de seguridad, SSE resiliente y fail-closed.

## Mejoras de Identidad y Experiencia (Fase 6 Base)
1. **Aros y LAN (`cara_dibujo.py`, `pantalla_remota*.py`):** Cian/esmeralda calmado; HTTPS `0.0.0.0:8765` sin PIN.
2. **Lyris y HUD (`pantalla_remota_*.py`):** Orbe central, botones >= 48px, CSS fluido, identidad Lyris en prompt/Vosk.
3. **Acción `activar_hud` y SSE (`pantalla_remota_accion.py`, `ecosistema_*.py`):** Detección inmediata en `respuesta_flujo.py`, failover SSE a polling 2s, altura `100dvh`.
4. **Consola y Visión Fresca (`ecosistema_gestor.py`, `multimodal_puente_app.py`):** UUID puro, telemetría anti-alucinación e invalidación en vivo (`fuente=zorder`).
5. **Archivos seguros y calidad (`recordatorios.py`, `habilidades_archivos.py`, `calidad_respuesta.py`):** Pipe/JSON/multilínea sin archivos vacíos; hashes/tokens válidos sin falso `token_corrupto`.
6. **Cerebro sabio y auto-entrenable (`cerebro_grafo.py`, `cerebro_planificador.py`, `cerebro_entrenamiento.py`):**
   - Grafo de Conocimiento Vivo en SQLite con sobreescritura de datos obsoletos.
   - Planificador multi-paso con auto-crítica verídica ante fallos parciales sin alucinaciones.
   - Búsqueda difusa tolerante a Whisper (< 50 ms) y segmentación TTS protegida contra cortes en tokens/código.
7. **Prioridad multi-paso y saneo Whisper (`respuesta_flujo.py`, `proveedores_cadenas.py`):**
   - `respuesta_flujo.py` prioriza multi-paso ante órdenes compuestas; retorno limpio sin doble voz en recordatorios.
   - Saneo fonético Whisper (`.tgit` -> `.txt`) y exclusión de `gpt-oss-20b` para prevenir 429 TPM.
8. **Memoria de trabajo y proactividad (`cerebro_trabajo.py`, `cerebro_proactivo.py`):**
   - `cerebro_trabajo.py` gestiona últimos 5 elementos y resuelve anáforas implícitas (*'léelo'*, *'agrégale...'*).
   - Guardarraíles anti-interrupción (cooldown 15 min, modo Privado/Noche), briefing diario y contexto IDE.
9. **Soporte Unicode y latencia en turnos (`cerebro_entrenamiento.py`, `respuesta_flujo.py`):**
   - Extracción de peticiones con soporte Unicode (`áéíóúüñ`); activación en 1 paso tras confirmación.
   - Saneo de latencia en turnos de texto/HUD descartando marcas de voz obsoletas.
10. **Autorización directa HUD LAN y captura técnica (`ecosistema_eventos.py`, `eventos.py`):**
   - Autorización automática en `ecosistema_eventos.py` para sesiones LAN del dueño (`tablet_hud`, `tablet`).
   - Captura de construcciones imperativas (*"crea un generador"*, *"haz una función"*).
11. **Cero atropello de voz, ejecución local y aceleración HUD (`cerebro_proactivo.py`, `respuesta_flujo.py`, `pantalla_remota_*.py`):**
   - Gracia inicial (>= 15s) en `MotorProactivo`, bloqueo si `app.hablando` o cola con audio, y coordinación con `iniciativa.py`.
   - Intercepción local (< 50 ms) de `escribir_archivo` y `leer_archivo` (con anáforas) leyendo contenido real.
   - Carril rápido de modelos ligeros, refresco acelerado en HUD (300/800ms) y subtítulo inmediato.
12. **Código real en habilidades, visión y RAG local (`cerebro_entrenamiento.py`, `vision_pantalla.py`, `cerebro_rag.py`):**
   - Generación de código Python funcional auditado por AST mediante LLM o generador determinista (`secrets`, `hashlib`).
   - Captura y análisis multimodal en memoria (JPEG b64, <= 1280px, sin disco) bajo demanda y modo Privado.
   - Indexación en SQLite FTS5 excluyendo rutas del sistema y secretos (`.env`), con contexto compacto (<= 900 chars).
13. **Modo Mentora socrática, presentación dinámica y nuevas expresiones (`cerebro_mentor.py`, `presentacion.py`, `cara_emociones.py`, `cara_dibujo.py`):**
   - `cerebro_mentor.py`: Gestor socrático con activación por voz, directiva compacta (218 chars <= 220) y consolidación en grafo.
   - `presentacion.py`: Detección de órdenes ("preséntate", "quién eres") y presentación viva (habilidades, proyectos, `orgullosa`).
   - `cara_emociones.py` y `cara_dibujo.py`: Rasgos visuales y prosodia Edge-TTS (`concentrada`, `firme`, `orgullosa`) delegados limpiamente.
14. **Visión multimodal real, filtro sensible técnico y refuerzo de mentora (`vision_pantalla.py`, `aprendizaje_datos.py`, `cerebro_mentor.py`, `respuesta_flujo.py`):**
   - `vision_pantalla.py`: Gemini REST nativo (`inline_data` base64) y resolución de ventana activa vía `app.sistema_multimodal`/`cerebro_trabajo`.
   - `aprendizaje_datos.py`: Filtro sensible regex estructurado que no descarta términos técnicos (*"columnas clave en Supabase"*).
   - `cerebro_mentor.py` y `respuesta_flujo.py`: Activación tolerante Whisper (*"modo mentor"*, *"enséñame a programar"*) y emoción `"concentrada"`.
