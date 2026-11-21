# TRASPASO DE PROYECTO — SILVESTRA

## 1. Quién es el dueño
- **Nombre:** Moisés (Panamá, `America/Panama`, español informal).
- **Perfil:** Principiante en programación (aprende sobre la marcha).
- **Comunicación:** Directo, párrafos cortos y explicaciones sencillas para teléfono móvil.

## 2. Metodología de trabajo
1. **Flujo de dos IAs:** IA planificadora redacta el prompt exacto; Moisés lo ejecuta en Gemini (Antigravity); Gemini entrega reporte conciso; Moisés reporta de vuelta.
2. **Reglas:** Honestidad técnica total, pruebas claras, commit previo y NUNCA pedir ni mostrar claves/tokens (`config.py`).

## 3. Silvestra y su arquitectura
Asistente personal con rostro interactivo PySide6, voz panameña (`es-PA-MargaritaNeural` / SAPI) y escucha Whisper.

### Módulos principales
- **`main.py`**: Orquestación y ciclo principal PySide6.
- **`cara_*.py` / `baile_audio.py` / `burbuja.py`**: Avatar (208 px), mirada reactiva, anillos HUD, 3 bailes y menú 3s.
- **`naturalidad.py` / `correcciones.py`**: Continuidad conversacional y autocorrección viva persistente.
- **`oido*.py`**: Stream persistente anti-crash, Silero VAD, feedback WAV y Whisper/Vosk.
- **`voz*.py`**: Síntesis `edge-tts`, mixer thread-safe, RMS labial, corte barge-in y modulación emocional.
- **`cerebro*.py`**: Prompt optimizado (<1350 tok), carril dual (`rapido`/`pro`), enrutador y acciones.
- **`proveedores*.py` / `sesion_http.py`**: Multi-LLM en cascada con pool Keep-Alive y streaming emocional.
- **`memoria*.py` / `persistencia_segura.py`**: Memoria duradera y persistencia JSON atómica (`NamedTemporaryFile` + `fsync` + `os.replace`).
- **`acciones.py`**: Registro central de capacidades del sistema (`acciones.registrar`).
- **`recordatorios.py` / `hilos.py`**: Recordatorios por voz y persistencia atómica con RLock.
- **`modos_sistema.py`**: 4 modos (`normal`, `programacion`, `estudio`, `noche`) en `estado.json` y HUD.
- **`iniciativa.py` / `iniciativa_contextual.py`**: Iniciativa contextual supervisable con cooldowns y revalidación.
- **`contexto_*.py`**: Context Engine (Etapas 1-4): sensor Win32, agregador 3 niveles, prompt bridge y SSE HUD.
- **`planificador*.py`**: Planificador de objetivos y tareas (Etapa 6): dependencias DFS, priorización y persistencia atómica.
- **`resumen*.py`**: Resúmenes web y video modularizados (`resumen_web.py`, `resumen_media.py`).
- **`telegram_*.py`**: Bot nativo y medios modularizados (`telegram_medios_proc.py`).
- **`pantalla_remota*.py` / `pantalla_biometria.py`**: HUD tablet SSE, telemetría y blindaje táctil.
- **`presencia.py` / `camara*.py` / `voz_dueno*.py`**: Biometría facial YuNet+SFace y vocal CAM++ multi-muestra.
- **`prueba_humo.py`**: Suite estricta de sintaxis y límite <= 15 KB sin excepciones.

### Reglas de oro de desarrollo
1. **Tamaño máximo:** Ningún archivo debe superar los **15 KB** (~15,360 bytes). TRASPASO.md <= 6.5 KB.
2. **Hilo principal Qt protegido:** Cero llamadas a Qt desde hilos secundarios (`app.cola` o señales).
3. **I/O en hilos secundarios:** Red, LLMs, TTS y procesos pesados siempre en hilos daemon.
4. **Acciones:** Toda capacidad se expone mediante `acciones.registrar(nombre, funcion, descripcion)`.
5. **Configuración y claves:** Exclusivamente en `config.py` (ignorado en git).

## 4. Estado actual (Fase 1 cerrada)
- PySide6, voz, cámara, Context Engine, HUD, iniciativa y planificador cerrados.
- Persistencia atómica y prueba de humo estricta operativas.

## 5. Tareas pendientes (Fase 2)
- [ ] **Rotar clave de Groq:** Clave expuesta en el pasado; rotar en `config.py` y Groq.
- [ ] **Módulo de diagnóstico central (`diagnostico.py`):** Monitorización integral de salud de subsistemas.
- [ ] **Cerebro premium ($5/mes):** Integrar proveedor de alta calidad con límite estricto de gasto.
- [ ] **Respaldo local:** Modelo SLM/LLM cuantizado local (Ollama / llama.cpp) offline.
- [ ] **Núcleo headless y nube:** Separar lógica para correr 24/7 en VPS con Telegram.

### Fase 2 — Etapa 1 cerrada
- Contratos puros `ejecucion_modelo.py`, registro thread-safe y resolución normalizada.
- Adaptador aislado de `acciones.py`: inventario descriptivo sin handlers ni efectos reales.

### Fase 2 — Etapa 2 cerrada
- Políticas centralizadas, huella SHA-256, vigencia, anti-replay y auditoría.

### Fase 2 — Etapa 3 cerrada
- Cola prioritaria, estados estrictos y workers acotados.
- Cancelación cooperativa y validación previa bajo `MotorPermisos`.

### Fase 2 — Etapa 4 cerrada
- Sandbox de archivos explícito con rechazo de traversal, UNC, reparse points y nombres reservados.
- Respaldo `.silvestra_respaldos`, escritura atómica y exclusión de respaldos en listados/búsquedas.

### Fase 2 — Etapa 5 cerrada
- Catálogo deny-by-default y identidad PID/creación/ruta para procesos Windows.
- Inicio con `shell=False`, supervisión acotada y cierre normal mediante `WM_CLOSE`.
- Sin shells arbitrarios ni cierre forzado; integración con permisos y motor concurrente.

### Fase 2 — Etapa 6 cerrada
- Inspección GUI segura, foco controlado y selectores estructurados.
- Credenciales protegidas y capturas PNG en sandbox.

### Fase 2 — Etapa 7 cerrada
- Evidencia positiva obligatoria y recuperación limitada a idempotentes.

### Fase 2 — Etapa 8 cerrada
- Orquestador global con modos restringido, supervisado y preautorizado.
- DAG validado, integración de motores y snapshots no bloqueantes.

### Fase 3 — Etapa 1 cerrada
- Percepción multimodal, cola concurrente, TTL y dedupe.
- Liberación de referencias y puentes pasivos a contexto/HUD/autonomía.

### Fase 3 — Etapa 2 cerrada
- Comprensión visual de PNG/JPEG/WebP y OCR desacoplado.
- Privacidad remota, caché visual y límites de memoria.

## 6. Guía de prompts para Gemini (Antigravity)
```text
Lee PROYECTO.md, TRASPASO.md y archivos relevantes. Define alcance, reglas .py/TRASPASO,
seguridad Qt, pruebas, tamaños exactos y actualización mínima de documentación.
```
