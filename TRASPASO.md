# TRASPASO DE PROYECTO — SILVESTRA

## 1. Quién es el dueño
- **Nombre:** Moisés.
- **Ubicación e idioma:** Panamá (zona horaria `America/Panama`), español informal.
- **Nivel:** Principiante en programación (aprende sobre la marcha).
- **Forma de comunicación:** Explica siempre en español sencillo, directo y con párrafos cortos (lee habitualmente desde el teléfono celular).

## 2. Metodología de trabajo
1. **Flujo con dos IAs:**
   - La IA consejera/planificadora (ej. ChatGPT/Claude) redacta el prompt exacto.
   - Moisés copia y pega ese prompt en Antigravity (Gemini).
   - Gemini edita el código, ejecuta pruebas y entrega un reporte.
   - Moisés le pasa el reporte a la IA consejera para revisión y siguiente paso.
2. **Reglas de interacción:**
   - **Honestidad total:** Si algo falló o un enfoque no conviene, dilo sin rodeos.
   - **Pasos de prueba claros:** Cada respuesta debe indicar cómo probar el cambio (comandos de terminal o frases por voz).
   - **Git commit previo:** Siempre hacer commit antes de cualquier cambio relevante.
   - **Seguridad y privacidad:** NUNCA pedir claves ni tokens en el chat. Las claves van únicamente en `config.py`.

## 3. Silvestra y su arquitectura
Silvestra es una asistente personal / compañera con rostro virtual interactivo en PyQt5, voz en español panameño (`es-PA-MargaritaNeural` / SAPI de respaldo) y comprensión de audio con Whisper.

### Módulos principales
- **`main.py`**: Punto de entrada, ciclo principal y orquestación con PyQt5.
- **`cara_qt.py` / `cara_dibujo.py` / `cara_movimiento.py` / `burbuja.py`**: Interfaz visual (rostro animado, mirada suave, paseo y boca sincronizada).
- **`oido.py` / `oido_flujo.py` / `oido_vad.py`**: Captura persistente anti-crash 0xc0000374, Silero VAD neuronal 16 kHz, anti-eco inteligente, barge-in y Whisper/Vosk.
- **`voz.py` / `voz_reproductor.py` / `voz_cache.py`**: Síntesis `edge-tts` modulada, reproductor thread-safe SDL/mixer, RMS labial, corte rápido barge-in y caché.
- **`cerebro.py` / `cerebro_prompt.py` / `cerebro_parser.py`**: Prompt (<2000 tokens), streaming y emociones/acciones.
- **`proveedores.py` / `proveedores_cadenas.py` / `sesion_http.py`**: Multi-LLM en cascada con pool HTTP Keep-Alive persistente y cooldown por modelo.
- **`memoria.py` / `memoria_busqueda.py` / `memoria_filtro.py`**: Memoria con fechas, filtro anti-meta y desduplicación.
- **`acciones.py`**: Registro central de acciones (`acciones.registrar`).
- **`recordatorios.py`**: Recordatorios por voz persistentes en disco (`recordatorios.json`).
- **`control_laptop.py` / `control_seguridad.py`**: Control de la laptop por niveles (libre, con código y prohibido) con lista permitida y auditoría.
- **`pantalla_remota.py` / `pantalla_remota_ui.py` / `pantalla_remota_datos.py`**: Servidor y HUD Jarvis en tiempo real para tablet.
- **`respaldo.py`**: Copia de seguridad zip fuera de Git (`~/Documents/Respaldos_Silvestra`) con rotación a 10 archivos sin claves.
- **`presencia.py` / `camara.py` / `camara_dueno.py`**: Presencia y biometría facial SFace + YuNet con banco multi-muestra (hasta 20), scoring top-2 y entrenamiento de cara por Telegram.
- **`voz_dueno.py` / `voz_dueno_banco.py` / `voz_dueno_registro.py`**: Biometría vocal CAM++ con banco multi-muestra (hasta 25), scoring top-2, aprendizaje `reforzar_mi_voz`, doble factor y modos de seguridad.
- **`prueba_humo.py`**: Suite de validación rápida de sintaxis, reglas de 15 KB y módulos clave.

### Reglas de oro de desarrollo
1. **Tamaño máximo:** Ningún archivo de código debe superar los **15 KB** (~15,360 bytes). Si crece, dividir en módulos especializados.
2. **Hilo principal Qt protegido:** Cero llamadas a Qt desde hilos secundarios. Toda comunicación hacia la interfaz va por `app.cola` o señales.
3. **I/O en hilos secundarios:** Red, APIs de LLM, TTS y operaciones pesadas siempre corren en hilos `threading.Thread(daemon=True)`.
4. **Acciones:** Toda nueva capacidad del asistente se expone mediante `acciones.registrar(nombre, funcion, descripcion)`.
5. **Configuración y claves:** Exclusivamente en `config.py` (ignorado en git). Plantilla pública en `config.example.py`.

## 4. Estado actual (lo que ya funciona)
- Rostro reactivo con mirada suave (`camara.py`), microexpresiones, parpadeo y aro facial (celeste/amarillo).
- Interrupción por voz (barge-in <500ms), filtro de eco y exclusión mutua de streams de audio (sin 0xc0000374).
- Síntesis en streaming (`cerebro_parser.py`) y voz panameña con `voz_reproductor.py` thread-safe.
- Silero VAD neuronal (`oido_vad.py`), anti-eco inteligente, Whisper determinista, Vosk offline y flujo anti-crash 0xc0000374.
- Prompt compacto (<1350 tokens) con inyección selectiva (`cerebro_categorias.py`) y multillm en cascada con Keep-Alive.
- Memoria duradera con fechas, filtro estricto anti-meta y desduplicación semántica (`memoria_filtro.py`).
- Acciones por voz: recuerdos, recordatorios persistentes, proveedores, control de escucha y modo estudio.
- Control de laptop por niveles (libre, peligroso exclusivo por Telegram con código y prohibido con auditoría).
- Respaldo automático fuera de Git (`respaldo.py`) con rotación a 10 archivos en Documentos sin claves.
- HUD Jarvis tablet a pantalla completa (100dvh horizontal, telemetría CPU/RAM/batería, notas, modo privado y SSE).
- Biometría vocal CAM++ multi-muestra (`voz_dueno*.py`), banco hasta 25 muestras con rotación FIFO (8 anclas fijas), scoring top-2, tolerancia comandos cortos, doble factor, modos Solo Dueño/Invitado y `reforzar_mi_voz`.
- Biometría facial SFace multi-muestra (`camara_dueno.py`, `camara.py`), banco hasta 20 fotos en `dueno.npy` (4 anclas fijas, FIFO), scoring top-2, descarte duplicados (>0.94) y aprendizaje enviando fotos con caption ('mi cara', 'entrenar cara') por Telegram.
- Suite de prueba de humo (`prueba_humo.py`) y arquitectura modular (todos los archivos <= 15 KB).

## 5. Tareas pendientes y pospuestas
- [ ] **Rotar clave de Groq:** Clave expuesta en el pasado; cambiarla en `config.py` y consola de Groq.
- [ ] **Cerebro premium ($5/mes):** Integrar proveedor de alta calidad con límite estricto de gasto como opción alternativa.
- [ ] **Respaldo local:** Modelo SLM/LLM cuantizado local (Ollama / llama.cpp) para operar 100% offline.
- [ ] **Iniciativa propia:** Saludos o comentarios espontáneos en momentos adecuados sin esperar turno.
- [ ] **Núcleo headless y nube:** Separar lógica para correr 24/7 en VPS conectada al bot de Telegram.
- [ ] **Anillo físico:** Pospuesto hasta contar con el hardware del anillo físico Bluetooth.

## 6. Guía de prompts para Gemini (Antigravity)

### Estructura base de un prompt
```text
Lee PROYECTO.md, TRASPASO.md y [archivos relevantes]. Haz git commit antes de empezar.
[Descripción clara y específica del cambio o corrección].
Respeta las reglas de oro:
- Archivos por debajo de 15 KB (si crece, crea módulo aparte).
- Nada de llamadas Qt directas desde hilos secundarios (usa app.cola).
- Todo trabajo pesado o de red en hilos secundarios daemon.
- Acciones registradas con acciones.registrar.
- No pidas claves ni inventes datos; español de Panamá.
Al terminar, muestra cómo probarlo, los tamaños de los archivos modificados y actualiza PROYECTO.md y TRASPASO.md.
```

### Qué pedir según el tipo de tarea
- **Corrección de bug:** Indicar el error exacto de `silvestra.log`, archivo donde ocurre y comportamiento esperado.
- **Nueva acción por voz:** Indicar nombre de la función, frases de activación natural, argumentos y qué debe responder en voz alta.
- **Nuevo proveedor o API:** Indicar endpoint OpenAI-compatible, variable en `config.example.py` (vacía por defecto) y modelos soportados.
- **Cambio visual en Qt:** Recordar cerrar siempre `QPainter` en bloque `try: ... finally: p.end()`.

---
*Nota: Para detalles técnicos extensos, diagramas y lecciones aprendidas, consulta siempre `PROYECTO.md`.*
