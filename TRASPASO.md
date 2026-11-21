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
- Fase 2 cerrada: permisos, ejecución, archivos, procesos, GUI, verificación y autonomía.

### Fase 2 — Etapas 1–8 cerradas
- Contratos, permisos, cola cancelable, sandbox, procesos y GUI seguros; evidencia y recuperación idempotente.
- Orquestador con modos restringido/supervisado/preautorizado, DAG y snapshots no bloqueantes.

### Fase 3 — Etapa 1 cerrada
- Percepción multimodal, cola concurrente, TTL y dedupe.
- Liberación de referencias y puentes pasivos a contexto/HUD/autonomía.

### Fase 3 — Etapa 2 cerrada
- Comprensión visual PNG/JPEG/WebP y OCR local.

### Fase 3 — Etapa 3 cerrada
- Comparación local de fotogramas y contexto temporal acotado.
- Fuente dual compatible con Camara y callable sintética.
- Sin almacenamiento permanente ni envío externo por defecto.

### Fase 3 — Etapa 4 cerrada
- Comprensión visual de interfaces: estructura Win32, OCR, formularios y alertas.
- Consulta NL pasiva sin acciones; campos sensibles enmascarados.
- Caché LRU de mapas/texto, sin imágenes o arrays, y remoto bloqueado por defecto.

### Corrección UI — estabilidad al minimizar
- Cola Qt drenada en lotes acotados con reprogramación de 1 ms.
- Movimiento y repintado suspendidos al minimizar o mostrar escritorio.

### Fase 3 — Etapa 5 (inteligencia auditiva)
- Clasificación espectral local, VAD opcional, eco TTS, historial temporal solo de metadatos y consultas recientes.
- Permiso de micrófono, grabación continua y envío externo desactivados por defecto; propuestas de autonomía pasivas.
- Suite sintética `test_inteligencia_auditiva.py`; heurística sin modelo neuronal dedicado.

### Fase 3 — Etapa 6 (integración multimodal)
- Coordinador de visión, cámara, interfaz, audio y contexto Windows; correlaciones probables separadas de hechos fuente.
- Historial sanitizado/acotado, anti-duplicados, tolerancia a fallos y avisos Qt por cola.
- Autorización externa desactivada; toda propuesta al orquestador es pasiva.

### Fase 3 — Etapa 7 (interpretación de situaciones)
- Evaluadores extensibles, incertidumbre explícita y memoria temporal con fusión, resolución y expiración.
- Hechos, relaciones probables, hipótesis y conclusiones verificadas permanecen separados; sin acciones automáticas.
- Suite sintética `test_interpretacion_situaciones.py`.

### Fase 3 — Etapa 8 (integración global)
- Puente global con ciclo de vida no bloqueante; cámaras, micrófono, captura continua y envío externo desactivados por defecto.
- Contexto conserva la última ventana externa no sensible; captura efímera cerrada en `finally`.
- Cerebro incluye observaciones e hipótesis separadas. Suite `test_validacion_global_fase3.py`; pendientes pruebas físicas autorizadas.
## Cierre Fase 4 — Etapa 8
Integración validada: SQLite/FTS5, formación, recuperación, grafo, linaje, consolidación, olvido y razonamiento trazable. El razonador es de solo lectura; contexto Windows en vivo permanece separado de recuerdos históricos. Validación E2E y regresión completa ejecutadas en almacenamiento aislado. Sin inicio de Fase 5.
