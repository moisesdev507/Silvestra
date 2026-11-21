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

## 5. Estado Fase 2–3
- Fase 2 (1–8): permisos, colas cancelables, sandbox, procesos/GUI seguros, evidencia y orquestación supervisada con DAG.
- Fase 3 (1–4): percepción multimodal, visión/OCR, cámara temporal e interfaces Win32; pasiva, privada y sin persistencia de capturas.
- Fase 3 (5–8): clasificación auditiva local, integración y correlación multimodal, interpretación temporal e integración global. Incertidumbre explícita; permisos de cámara/micrófono/envío externo apagados. Suite global disponible; pruebas físicas pendientes.
- Qt: cola acotada, repintado suspendido al minimizar; al despertar restaura solo el avatar, no el panel Casa.

## Fase 4 — Etapas 1–8
Memoria cognitiva SQLite/FTS5: formación, recuperación, grafo, linaje, consolidación, olvido y razonamiento trazable. Aislamiento por usuario; consultas de razonamiento de solo lectura. Contexto Windows vivo separado de recuerdos históricos; regresión E2E validada en almacenamiento aislado.

## Fase 5 — Etapa 1
Motor determinista de razonamiento (`razonamiento_modelos.py`, `razonamiento_fuentes.py`, `razonamiento_evaluador.py`, `razonamiento_motor.py`) integrado en Cerebro. Reutiliza el paquete de memoria ya calculado; separa estado vivo, hechos explícitos, inferencias, hipótesis y conclusiones trazables. Cancelable, de solo lectura y sin acciones. Suite `test_razonamiento_inteligente_fase5_etapa1.py`; no iniciar Etapa 2 sin revisión.

## Fase 5 — Etapa 2
Planificación reutiliza el DAG de `planificador_modelo.py`; evaluación de alternativas/riesgos, progreso y replanificación incremental se guardan por usuario en la SQLite cognitiva. Cerebro solo genera planes ante pedidos explícitos. Recomendación, aprobación humana y autorización de ejecución son estados independientes; no hay ejecución autónoma.

## Fase 5 — Etapa 3
Aprendizaje experiencial trazable sobre SQLite cognitiva: patrones requieren 3 fuentes independientes. Verificación publica informes a un adaptador de fondo; razonamiento y planificación reciben lecciones históricas orientativas. Sin cambios automáticos a permisos/código.
