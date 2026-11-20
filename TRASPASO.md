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
- Avatar PySide6 compacto (208 px), anillos reactivos y 3 bailes rítmicos locales.
- Doble confirmación de 3s en reinicio/despertar/renacer en menú y tablet HUD.
- Naturalidad, autocorrección viva, barge-in (<500ms) y filtro de eco Silero VAD.
- Context Engine Etapas 1-5 e Iniciativa Contextual supervisable (`iniciativa_contextual.py`).
- Planificador Inteligente Etapa 6 (`planificador.py`, `planificador_modelo.py`).
- Persistencia atómica blindada en `memoria.py` y `recordatorios.py` (`persistencia_segura.py`).
- Código muerto eliminado (`cara.py`) y módulos > 15 KB modularizados (`resumen`, `telegram_medios`).
- Suite `prueba_humo.py` 100% PASS sin listas blancas legacy (100% archivos <= 15 KB).

## 5. Tareas pendientes (Fase 2)
- [ ] **Rotar clave de Groq:** Clave expuesta en el pasado; rotar en `config.py` y Groq.
- [ ] **Módulo de diagnóstico central (`diagnostico.py`):** Monitorización integral de salud de subsistemas.
- [ ] **Cerebro premium ($5/mes):** Integrar proveedor de alta calidad con límite estricto de gasto.
- [ ] **Respaldo local:** Modelo SLM/LLM cuantizado local (Ollama / llama.cpp) offline.
- [ ] **Núcleo headless y nube:** Separar lógica para correr 24/7 en VPS con Telegram.

## 6. Guía de prompts para Gemini (Antigravity)
```text
Lee PROYECTO.md, TRASPASO.md y [archivos relevantes]. Haz git commit antes de empezar.
[Descripción clara y específica del cambio o corrección].
Reglas de oro:
- Archivos .py <= 15 KB (si crece, dividir en módulos) y TRASPASO.md <= 6.5 KB.
- Nada de llamadas Qt directas desde hilos secundarios (usa app.cola).
- Todo trabajo pesado o de red en hilos secundarios daemon.
- No pidas claves ni inventes datos; español de Panamá.
Al terminar, muestra cómo probarlo, tamaños exactos y actualiza PROYECTO.md y TRASPASO.md.
```
