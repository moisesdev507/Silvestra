# TRASPASO — LYRIS // SILVESTRA

## Arquitectura y reglas
Asistente personal modular Python/Windows con avatar PySide6, voz/escucha, percepción y Context Engine, memoria cognitiva, planificación, permisos y ejecución supervisada. La UI solo se toca desde Qt; los hilos secundarios comunican mediante `app.cola`/señales. Máximo 15,360 B por `.py`; máximo 6,656 B aquí. No exponer claves ni tokens. Las inferencias no son hechos ni autorizan acciones. Toda operación sensible requiere confirmación y permisos centrales.

## Componentes
- `main.py`, `eventos.py`, `cara_*.py`: aplicación Qt, avatar holográfico y cola de eventos.
- `voz*.py`, `oido*.py`, `audio_*.py`: TTS, reproducción/RMS, captura y VAD.
- `cerebro*.py`, `respuesta_flujo.py`, `proveedores*.py`: conversación, prompt e identidad Lyris.
- `memoria*.py`, `persistencia_segura.py`: memoria cognitiva SQLite/FTS5, linaje y consolidación.
- `contexto_*.py`, `multimodal_*.py`, `percepcion_*.py`, `vision_*.py`: contexto Windows y percepción pasiva.
- `razonamiento_*.py`, `planificacion_*.py`, `experiencia_*.py`: planes y aprendizaje trazable.
- `ejecucion_*.py`, `permisos_*.py`, `acciones.py`: ejecución validada y permisos por niveles.
- `iniciativa*.py`, `recordatorios.py`, `telegram_*.py`: iniciativa cancelable y puente Telegram.
- `pantalla_remota*.py`, `ecosistema_*.py`: HUD web Galaxy Tab A7, SSE y auto-enlace LAN seguro.

## Fases cerradas
- Fase 1 a Fase 5: núcleo cognitivo, percepción, permisos supervisados, memoria y aprendizaje validados.
- Fase 6 (Etapas 1 y 2): contratos sanitizados, puente de seguridad, SSE resiliente y gestión fail-closed de dispositivos.

## Mejoras de Identidad y Experiencia (Fase 6 Base)
1. **Aros HUD en reposo (`cara_dibujo.py`):** Los aros orbitales alrededor del rostro muestran su tono cian y verde esmeralda calmado (`vel=24.0`, pulso suave) cuando el micrófono está apagado o en reposo. El ámbar/amarillo se activa exclusivamente ante escucha activa o procesamiento/pensamiento.
2. **Auto-enlace LAN sin fricción (`pantalla_remota*.py`, `ecosistema_*.py`):** Si existen `hud_cert.pem` y `hud_key.pem`, el servidor arranca automáticamente en HTTPS escuchando en `0.0.0.0:8765`. Clientes en la red local privada (RFC 1918) son emparejados automáticamente en `/api/sesion` mediante `emparejar_lan()` recibiendo cookies de sesión sin ventanas emergentes de PIN ni contraseñas. Orígenes externos no autorizados continúan bloqueados fail-closed.
3. **Identidad vocal y visual "Lyris":** Ventana de PC, prompt del sistema (`SOBRE_MI`), `alma.txt`, `memoria.json` y HUD identifican a Lyris. Vosk offline reconoce "lyris", variantes fonéticas ("liris", "iris", "lira", "liria") y compatibilidad con "silvestra".
4. **HUD Galaxy Tab A7 & Esfera de Energía (`pantalla_remota_tema.py`, `pantalla_remota_ui.py`):** Rediseño holográfico con estética de esfera de energía cibernética en el orbe central, controles táctiles ergonómicos $\ge 48$ px, barras fluidas con transición CSS para CPU/RAM/Batería y reloj local instantáneo al conectar.
