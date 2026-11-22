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
1. **Aros HUD en reposo (`cara_dibujo.py`):** Cian/esmeralda calmado (`vel=24.0`) en reposo. Ámbar exclusivo para escucha activa o pensamiento.
2. **Auto-enlace LAN sin fricción (`pantalla_remota*.py`, `ecosistema_*.py`):** HTTPS en `0.0.0.0:8765` con `hud_cert.pem`. Clientes LAN emparejados en `/api/sesion` sin PIN.
3. **Identidad vocal y visual "Lyris":** Prompt (`SOBRE_MI`), `alma.txt`, `memoria.json` y HUD identifican a Lyris. Vosk reconoce "lyris" y "silvestra".
4. **HUD Galaxy Tab A7 & Esfera de Energía (`pantalla_remota_tema.py`, `pantalla_remota_ui.py`):** Orbe central de energía, botones $\ge 48$ px, CSS fluido y reloj instantáneo.
5. **Acción `activar_hud` y cascada rápida (`pantalla_remota_accion.py`, `proveedores_stream.py`):** Detección inmediata en `respuesta_flujo.py` para arrancar en LAN sin latencia LLM. Groq prioriza `llama-3.1-8b-instant`.
6. **Botones y SSE HUD Tablet (`pantalla_remota_*.py`, `ecosistema_*.py`):** Asignación de puente, validación de origen, polling 2s de respaldo manteniendo `EN LÍNEA` y altura `100dvh`.
7. **Consola Tablet y Visión Fresca (`ecosistema_gestor.py`, `multimodal_puente_app.py`, `multimodal_ventana_win32.py`):** `device_id` UUID puro, prompt anti-alucinación y caché invalidada en vivo (`fuente=zorder`).
8. **Recordatorios y archivos seguros (`recordatorios.py`, `memoria_formacion.py`, `habilidades_archivos.py`):** Números en palabras. `escribir_archivo` admite pipe, JSON y multilínea, impidiendo archivos vacíos de 0 B.
9. **Filtro lingüístico (`calidad_respuesta.py`):** Tokens alfanuméricos reconocidos como claves y hashes (ej. `V9k!`), suprimiendo falsos positivos de `token_corrupto`.
10. **Cerebro sabio y auto-entrenable (`cerebro_grafo.py`, `cerebro_planificador.py`, `cerebro_entrenamiento.py`, `cerebro_parser.py`):**
   - Grafo de Conocimiento Vivo: Tablas aditivas `grafo_nodos` y `grafo_relaciones` en SQLite con sobreescritura de datos obsoletos y consulta contextual compacta en prompt.
   - Planificador multi-paso: Encadena hasta 3 acciones reales (`planificar -> ejecutar -> verificar`) con auto-crítica verídica ante fallos parciales sin alucinaciones.
   - Auto-aprendizaje y voz sin cortes: Búsqueda difusa tolerante a Whisper (`SequenceMatcher`, `< 50 ms`), auto-propuesta proactiva de habilidades técnicas y segmentación TTS protegida contra cortes en contraseñas (`V9k!`), tokens y código (`prueba.py`).
11. **Prioridad multi-paso, voz unificada y saneo Whisper (`respuesta_flujo.py`, `cerebro_planificador.py`, `habilidades_archivos.py`, `proveedores_cadenas.py`):**
   - `respuesta_flujo.py` prioriza `cerebro_planificador` ante órdenes compuestas y retorna `accion=None`, impidiendo la re-ejecución errónea en `eventos.py` y la doble voz en recordatorios.
   - Whisper tolerante fonéticamente (`llea`, `lea`, `crea`) y saneo de extensiones mal transcritas (`.tgit`, `.tequisde` -> `.txt`).
   - Generación automática de contenido estructurado para archivos en órdenes compuestas.
   - Exclusión de `openai/gpt-oss-20b` en Groq para prevenir enfriamientos por HTTP 429 TPM.
12. **Memoria de trabajo corta y motor proactivo situacional (`cerebro_trabajo.py`, `cerebro_proactivo.py`):**
   - `cerebro_trabajo.py` mantiene los últimos 5 elementos contextuales y resuelve anáforas implícitas (*'léelo'*, *'agrégale...'*). Inyecta directiva compacta $\le$ 140 B en prompt.
   - `cerebro_proactivo.py` implementa guardarraíles anti-interrupción (cooldown 15 min, modo Privado/Noche) y reglas situacionales: briefing diario ($\le$ 25 palabras), contexto de proyecto en IDE y cuidado nocturno.
13. **Soporte Unicode en auto-aprendizaje y latencia real en texto (`cerebro_entrenamiento.py`, `respuesta_flujo.py`, `voz.py`, `eventos.py`):**
   - Extracción de peticiones técnicas con soporte Unicode completo (`áéíóúüñ`), impidiendo que palabras como *'contraseña'* se corten en *'contrase'*.
   - Activación inmediata de habilidades en 1 paso tras confirmación y eliminación de propuestas duplicadas en log.
   - Saneo de métrica de latencia en turnos de texto/HUD descartando marcas de voz obsoletas (> 30s).
14. **Autorización directa HUD LAN y captura de habilidades (`ecosistema_eventos.py`, `eventos.py`, `cerebro_entrenamiento.py`):**
   - Autorización en `ecosistema_eventos.py` para sesiones LAN del dueño (`tablet_hud`, `tablet`), suprimiendo el falso bloqueo de aprobación pendiente y cortes de voz.
   - Soporte en `detectar_peticion_tecnica_nueva` para verbos y construcciones imperativas (*"crea un generador"*, *"haz una función"*), asegurando propuesta, confirmación y activación directa.
