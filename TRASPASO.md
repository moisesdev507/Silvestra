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
1. **Aros HUD en reposo (`cara_dibujo.py`):** Tono cian/verde esmeralda calmado (`vel=24.0`) con micrófono apagado o en reposo. Ámbar exclusivo para escucha activa o pensamiento.
2. **Auto-enlace LAN sin fricción (`pantalla_remota*.py`, `ecosistema_*.py`):** HTTPS en `0.0.0.0:8765` con `hud_cert.pem`. Clientes en LAN privada (RFC 1918) emparejados automáticamente en `/api/sesion` sin PIN.
3. **Identidad vocal y visual "Lyris":** Prompt (`SOBRE_MI`), `alma.txt`, `memoria.json` y HUD identifican a Lyris. Vosk offline reconoce "lyris", variantes fonéticas y "silvestra".
4. **HUD Galaxy Tab A7 & Esfera de Energía (`pantalla_remota_tema.py`, `pantalla_remota_ui.py`):** Orbe central con estética de energía cibernética, botones táctiles $\ge 48$ px, barras CSS fluidas y reloj local instantáneo.
5. **Acción `activar_hud` y cascada rápida (`pantalla_remota_accion.py`, `proveedores_stream.py`):** Acción `activar_hud` en `acciones.py`. Detección inmediata en `respuesta_flujo.py` para arrancar en LAN sin latencia LLM. Groq prioriza `llama-3.1-8b-instant` con timeout $\le 3.5$ s.
6. **Botones y SSE HUD Tablet (`pantalla_remota_*.py`, `ecosistema_*.py`):** Servidor asigna puente. Validación de origen en GET y `/eventos`. Polling de respaldo cada 2s a `/api/panel/estado` manteniendo `EN LÍNEA`. Ejecución directa de botones. Altura `100dvh` sin recorte.
7. **Consola Tablet y Visión Fresca (`ecosistema_gestor.py`, `multimodal_puente_app.py`, `multimodal_ventana_win32.py`):** `device_id` con UUID puro. Prompt anti-alucinación sobre estado en vivo. `consultar_entorno_actual` invalida caché en vivo (`fuente=zorder` vía `EnumDesktopWindows`).
8. **Recordatorios sin falso bloqueo y archivos seguros (`recordatorios.py`, `memoria_formacion.py`, `habilidades_archivos.py`):** Admite números en palabras (`un`, `medio`, `dos`). Sin falsos rechazos en memoria. `escribir_archivo` admite pipe, JSON y multilínea, rechazando nombres sin contenido con mensaje instructivo impidiendo archivos vacíos de 0 B.
9. **Filtro de calidad lingüística (`calidad_respuesta.py`):** Tokens alfanuméricos (`any(c.isdigit()) and any(c.isalpha())`) reconocidos como contraseñas, tokens y hashes (ej. `V9k!`), suprimiendo falsos positivos de `token_corrupto` en respuestas coherentes en español.
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
   - `cerebro_trabajo.py` mantiene los últimos 5 elementos contextuales (`ultimo_archivo`, `ultima_carpeta`, `ultima_ventana`, `ultimo_recordatorio`, `ultima_habilidad`) y resuelve anáforas implícitas (*'léelo'*, *'agrégale...'*). Inyecta directiva compacta $\le$ 140 B en prompt.
   - `cerebro_proactivo.py` implementa guardarraíles anti-interrupción (cooldown de 15 min, bloqueo en modo Privado, restricción en modo Noche) y reglas situacionales: briefing diario ($\le$ 25 palabras), contexto de proyecto en IDE y cuidado nocturno.
