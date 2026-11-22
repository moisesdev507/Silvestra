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
- `pantalla_remota*.py`, `ecosistema_*.py`: HUD web Galaxy Tab A7, SSE, tema esfera de energía y auto-enlace LAN.
- `habilidades_archivos.py`, `aprendiz_habilidades.py`: manipulación segura de archivos y auto-aprendizaje con auditoría AST.

## Fases cerradas
- Fase 1 a Fase 5: núcleo cognitivo, percepción, permisos supervisados, memoria y aprendizaje validados.
- Fase 6 (Etapas 1 y 2): contratos sanitizados, puente de seguridad, SSE resiliente y gestión fail-closed de dispositivos.

## Mejoras de Identidad y Experiencia (Fase 6 Base)
1. **Aros HUD en reposo (`cara_dibujo.py`):** Los aros orbitales alrededor del rostro muestran su tono cian y verde esmeralda calmado (`vel=24.0`, pulso suave) cuando el micrófono está apagado o en reposo. El ámbar/amarillo se activa exclusivamente ante escucha activa o procesamiento/pensamiento.
2. **Auto-enlace LAN sin fricción (`pantalla_remota*.py`, `ecosistema_*.py`):** Si existen `hud_cert.pem` y `hud_key.pem`, el servidor arranca automáticamente en HTTPS escuchando en `0.0.0.0:8765`. Clientes en la red local privada (RFC 1918) son emparejados automáticamente en `/api/sesion` mediante `emparejar_lan()` recibiendo cookies de sesión sin ventanas emergentes de PIN ni contraseñas.
3. **Identidad vocal y visual "Lyris":** Ventana de PC, prompt del sistema (`SOBRE_MI`), `alma.txt`, `memoria.json` y HUD identifican a Lyris. Vosk offline reconoce "lyris", variantes fonéticas ("liris", "iris", "lira", "liria") y compatibilidad con "silvestra".
4. **HUD Galaxy Tab A7 & Esfera de Energía (`pantalla_remota_tema.py`, `pantalla_remota_ui.py`):** Rediseño holográfico con estética de esfera de energía cibernética en el orbe central, controles táctiles ergonómicos $\ge 48$ px, barras fluidas con transición CSS para CPU/RAM/Batería y reloj local instantáneo al conectar.
5. **Acción `activar_hud` y cascada rápida (`pantalla_remota_accion.py`, `proveedores_cadenas.py`, `proveedores_stream.py`):** Acción `activar_hud` y alias (`activar_pantalla_remota`, `activar_tablet`, `abrir_hud`) en `acciones.py` y `cerebro_categorias.py`. Detección inmediata en `respuesta_flujo.py` y `cerebro.py` para arrancar el servidor en LAN (`0.0.0.0:8765`) y responder por voz sin latencia LLM. Groq prioriza `llama-3.1-8b-instant` y `llama-3.3-70b-versatile` con timeout $\le 3.5$ s.
6. **Reparación de Botones y SSE HUD Tablet (`pantalla_remota_*.py`, `ecosistema_*.py`):** Servidor asigna `servidor.puente = self.puente`. Validación de origen en GET y `/eventos` sin forzar mutación. Token `X-Device-Token` y cookies `SameSite=Lax`. Polling de respaldo cada 2s a `/api/panel/estado` manteniendo estado `EN LÍNEA` en tiempo real. Ejecución directa y controlada de botones del panel. Altura fijada a `100dvh` sin recorte de clima. Sensibilidad vocal ajustada (`umbral=0.35`, clips cortos $\le 2.5$ s a `0.30`, VAD threshold `0.40`).
7. **Consola Tablet y Visión Fresca (`ecosistema_gestor.py`, `cerebro_prompt.py`, `multimodal_puente_app.py`, `multimodal_ventana_win32.py`):** `emparejar_lan()` emite UUID puros resolviendo error de validación en `CommandRequest`. Prompt con directiva anti-alucinación visual exigiendo responder estrictamente sobre el estado en vivo. `consultar_entorno_actual` invalida caché en vivo (`fuente=zorder` vía `EnumDesktopWindows(OpenInputDesktop)`).
8. **Recordatorios sin falso bloqueo, acciones de archivos y aprendiz de habilidades (`recordatorios.py`, `memoria_formacion.py`, `respuesta_flujo.py`, `habilidades_archivos.py`, `aprendiz_habilidades.py`):**
   - Recordatorios: parseo de tiempo soporta palabras numéricas (`un`, `una`, `medio`, `dos`, etc.). Detección de recordatorios temporales no clasifica como orden de memoria episódica a largo plazo (`accion: ninguna`), evitando el rechazo `"No puedo guardar ese dato de forma segura"`. Enrutamiento inmediato en `respuesta_flujo.py` con confirmación horaria y reflejo en el HUD.
   - Archivos: `habilidades_archivos.py` (`escribir_archivo`, `leer_archivo`, `listar_archivos`) acotadas a `workspace_lyris/`, `Desktop` y `Documents`, bloqueando rutas del sistema, código del núcleo, path traversal y extensiones peligrosas.
   - Aprendiz de Habilidades: `aprendiz_habilidades.py` con persistencia en `habilidades_aprendidas/` y `registro.json`. Auditoría AST obligatoria (`auditar_codigo`), bloqueo de llamadas y módulos peligrosos (`subprocess`, `ctypes`, `winreg`, `os.system`, `eval`), flujo de confirmación explícita del dueño (`confirmar_habilidad`) y carga dinámica automática al arrancar.
