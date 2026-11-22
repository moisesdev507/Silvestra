# TRASPASO — LYRIS // SILVESTRA

## Arquitectura y reglas
Asistente personal modular Python/Windows con avatar PySide6, voz/escucha, percepción y Context Engine, memoria cognitiva, planificación, permisos y ejecución supervisada. La UI solo se toca desde Qt; hilos secundarios comunican por `app.cola`/señales. Límite: <= 15,360 B por `.py`; <= 6,656 B aquí. Las inferencias no son hechos ni autorizan acciones. Operaciones sensibles requieren confirmación.

## Componentes
- `main.py`, `eventos.py`, `cara_*.py`: aplicación Qt, avatar holográfico y cola de eventos.
- `voz*.py`, `oido*.py`, `audio_*.py`: TTS, reproducción/RMS, captura y VAD.
- `cerebro*.py`, `respuesta_flujo.py`, `proveedores*.py`: conversación, prompt e identidad Lyris.
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
8. **Recordatorios sin falso bloqueo y archivos seguros (`recordatorios.py`, `memoria_formacion.py`, `habilidades_archivos.py`):**
   - Recordatorios: admite números en palabras (`un`, `medio`, `dos`). `memoria_formacion` no confunde recordatorios temporales con memoria episódica. Programación inmediata en `respuesta_flujo.py` reflejada en HUD.
   - Archivos: `habilidades_archivos.py` (`escribir_archivo`, `leer_archivo`, `listar_archivos`) acotadas a `workspace_lyris/`, `Desktop` y `Documents`, bloqueando núcleo, traversal y extensiones peligrosas.
9. **Escritura con contenido, filtro contraseñas y habilidades en vivo (`habilidades_archivos.py`, `calidad_respuesta.py`, `aprendiz_habilidades.py`, `respuesta_flujo.py`):**
   - Archivos: `escribir_archivo` admite pipe (`ruta | contenido`), JSON y multilínea. Rechaza nombres sin contenido con mensaje instructivo impidiendo archivos vacíos de 0 B. Prompt y `acciones.py` instruyen redactar tras el pipe.
   - Calidad lingüística: `calidad_respuesta.py` no marca tokens alfanuméricos como corruptos (`any(c.isdigit()) and any(c.isalpha())`), permitiendo contraseñas, tokens y hashes (ej. `V9k!`), suprimiendo falsos positivos.
   - Habilidades en vivo: `respuesta_flujo.py` detecta de inmediato órdenes de aprendizaje (`aprende a...`) y aprobación (`aprueba la habilidad...`), y ejecuta habilidades aprobadas con tolerancia fonética de Whisper (`"contrasiña" -> "contrasena"`). Sincronización en demanda con `cerebro_categorias.py` y `ACCIONES.VIVAS`.
