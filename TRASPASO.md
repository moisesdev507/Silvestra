# TRASPASO — LYRIS // SILVESTRA

## Arquitectura y reglas
Asistente modular Python/Windows con avatar PySide6, voz/escucha, Context Engine, memoria, planificación y permisos. UI solo desde Qt; hilos secundarios usan `app.cola`/señales. Límite: <= 15,360 B por `.py`; <= 6,656 B aquí. Inferencias no autorizan acciones; operaciones sensibles requieren confirmación.

## Componentes
- `main.py`, `eventos.py`, `cara_*.py`: aplicación Qt, avatar holográfico y cola de eventos.
- `voz*.py`, `oido*.py`, `audio_*.py`: TTS, reproducción/RMS, captura y VAD.
- `cerebro*.py`, `respuesta_flujo.py`, `proveedores*.py`: conversación, prompt e identidad Lyris.
- `cerebro_grafo.py`, `cerebro_planificador.py`, `cerebro_entrenamiento.py`: grafo, multi-paso y auto-aprendizaje.
- `cerebro_trabajo.py`, `cerebro_proactivo.py`, `cerebro_mentor.py`: memoria corta, proactividad y modo mentora.
- `memoria*.py`, `persistencia_segura.py`, `cerebro_rag.py`: persistencia SQLite/FTS5, linaje y RAG seguro.
- `contexto_*.py`, `multimodal_*.py`, `vision_*.py`: percepción Windows, vision de pantalla y telemetría.
- `ejecucion_*.py`, `permisos_*.py`, `acciones.py`: ejecución validada y permisos por niveles.
- `iniciativa*.py`, `recordatorios.py`, `telegram_*.py`: iniciativa cancelable y puente Telegram.
- `pantalla_remota*.py`, `ecosistema_*.py`, `app_movil_*.py`: HUD tablet, PWA móvil, SSE y red LAN/Tailscale.
- `habilidades_archivos.py`, `aprendiz_habilidades.py`: archivos y habilidades con auditoría AST.

## Fases cerradas
- Fase 1 a Fase 5: núcleo cognitivo, percepción, permisos supervisados, memoria y aprendizaje validados.
- Fase 6: contratos sanitizados, puente de seguridad, SSE resiliente y fail-closed.

## Mejoras de Identidad y Experiencia (Fase 6)
1. **Aros y LAN (`cara_dibujo.py`, `pantalla_remota*.py`):** Cian/esmeralda; HTTPS `0.0.0.0:8765` sin PIN.
2. **Lyris y HUD (`pantalla_remota_*.py`):** Orbe central, botones >= 48px, CSS fluido, identidad Lyris.
3. **Acción `activar_hud` y SSE (`pantalla_remota_accion.py`, `ecosistema_*.py`):** Detección inmediata en `respuesta_flujo.py`, failover SSE a polling 2s, altura `100dvh`.
4. **Consola y Visión Fresca (`ecosistema_gestor.py`, `multimodal_puente_app.py`):** UUID puro, telemetría anti-alucinación e invalidación en vivo (`fuente=zorder`).
5. **Archivos seguros y calidad (`recordatorios.py`, `habilidades_archivos.py`, `calidad_respuesta.py`):** Formatos robustos sin vacíos; tokens válidos sin falso `token_corrupto`.
6. **Cerebro sabio y auto-entrenable (`cerebro_grafo.py`, `cerebro_planificador.py`, `cerebro_entrenamiento.py`):**
   - Grafo de Conocimiento Vivo en SQLite con sobreescritura de datos obsoletos.
   - Planificador multi-paso con auto-crítica verídica ante fallos parciales sin alucinaciones.
   - Búsqueda difusa tolerante a Whisper (< 50 ms) y segmentación TTS protegida contra cortes.
7. **Prioridad multi-paso y saneo Whisper (`respuesta_flujo.py`, `proveedores_cadenas.py`):**
   - `respuesta_flujo.py` prioriza multi-paso ante órdenes compuestas; retorno limpio sin doble voz.
   - Saneo fonético Whisper (`.tgit` -> `.txt`) y exclusión de `gpt-oss-20b` para prevenir 429 TPM.
8. **Memoria de trabajo y proactividad (`cerebro_trabajo.py`, `cerebro_proactivo.py`):**
   - `cerebro_trabajo.py` gestiona últimos 5 elementos y resuelve anáforas (*'léelo'*, *'agrégale...'*).
   - Guardarraíles anti-interrupción (cooldown 15 min, Privado/Noche), briefing y contexto IDE.
9. **Soporte Unicode y latencia (`cerebro_entrenamiento.py`, `respuesta_flujo.py`):**
   - Extracción con Unicode (`áéíóúüñ`); activación en 1 paso tras confirmación.
   - Saneo de latencia en turnos de texto/HUD descartando marcas de voz obsoletas.
10. **Autorización directa HUD LAN y captura técnica (`ecosistema_eventos.py`, `eventos.py`):**
    - Autorización automática en `ecosistema_eventos.py` para sesiones LAN del dueño (`tablet_hud`, `tablet`).
    - Captura de construcciones imperativas (*"crea un generador"*, *"haz una función"*).
11. **Cero atropello de voz, ejecución local y aceleración HUD (`cerebro_proactivo.py`, `respuesta_flujo.py`, `pantalla_remota_*.py`):**
    - Gracia inicial (>= 15s) en `MotorProactivo`, bloqueo si `app.hablando` o cola con audio, y coordinación con `iniciativa.py`.
    - Intercepción local (< 50 ms) de `escribir_archivo` y `leer_archivo` (con anáforas) leyendo contenido real.
    - Carril rápido de modelos ligeros, refresco acelerado en HUD (300/800ms) y subtítulo inmediato.
12. **Código real en habilidades, visión y RAG local (`cerebro_entrenamiento.py`, `vision_pantalla.py`, `cerebro_rag.py`):**
    - Generación de código Python funcional auditado por AST mediante LLM o generador determinista.
    - Captura multimodal en memoria (JPEG b64, <= 1280px, sin disco) bajo demanda y modo Privado.
    - Indexación en SQLite FTS5 excluyendo rutas del sistema y secretos (`.env`), con contexto compacto (<= 900 chars).
13. **Modo Mentora socrática, presentación y nuevas expresiones (`cerebro_mentor.py`, `presentacion.py`, `cara_emociones.py`, `cara_dibujo.py`):**
    - `cerebro_mentor.py`: Gestor socrático con activación por voz, directiva compacta (218 chars <= 220) y grafo.
    - `presentacion.py`: Detección de órdenes ("preséntate", "quién eres") y presentación viva (`orgullosa`).
    - `cara_emociones.py` y `cara_dibujo.py`: Rasgos visuales y prosodia Edge-TTS (`concentrada`, `firme`, `orgullosa`).
14. **Visión multimodal real, filtro sensible y refuerzo de mentora (`vision_pantalla.py`, `aprendizaje_datos.py`, `cerebro_mentor.py`):**
    - `vision_pantalla.py`: Gemini REST nativo (`inline_data` base64) y resolución de ventana activa.
    - `aprendizaje_datos.py`: Filtro sensible regex estructurado que no descarta términos técnicos.
    - `cerebro_mentor.py` y `respuesta_flujo.py`: Activación tolerante Whisper y emoción `"concentrada"`.
15. **App móvil PWA y Tailscale (`app_movil_ui.py`, `app_movil_html.py`, `app_movil_audio.py`, `pantalla_remota_api.py`):**
    - Vista mobile-first estilo ChatGPT en `/movil` con avatar SVG vivo, botones Mentora/Privado y PWA (`/manifest.json`, `/sw.js`).
    - Soporte de subred Tailscale CGNAT (`100.64.0.0/10`) y LAN privada en `pantalla_remota_api.py`.
    - Endpoint `/api/movil/voz` con transcripción Whisper en memoria, ejecución en núcleo Lyris y TTS en base64.
