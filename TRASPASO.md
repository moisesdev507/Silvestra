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
- **`oido.py`**: Micrófono (`sounddevice`), VAD ágil (0.55s), barge-in, normalización y Whisper/Vosk.
- **`voz.py` / `voz_reproductor.py` / `voz_cache.py`**: Síntesis `edge-tts` modulada, reproductor thread-safe SDL/mixer, RMS labial, corte rápido barge-in y caché.
- **`cerebro.py` / `cerebro_prompt.py` / `cerebro_parser.py`**: Prompt (<2000 tokens), streaming y emociones/acciones.
- **`proveedores.py` / `proveedores_cadenas.py` / `sesion_http.py`**: Multi-LLM en cascada con pool HTTP Keep-Alive persistente y cooldown por modelo.
- **`memoria.py` / `memoria_busqueda.py`**: Memoria permanente con fechas, categorías y anti-invención.
- **`acciones.py`**: Registro central de acciones (`acciones.registrar`).
- **`recordatorios.py`**: Recordatorios por voz persistentes en disco (`recordatorios.json`).
- **`control_laptop.py` / `control_seguridad.py`**: Control de la laptop por niveles (libre, con código y prohibido) con lista permitida y auditoría.
- **`pantalla_remota.py` / `casa_web*.py`**: Servidor local HTTP/SSE, panel tablet y casa virtual 2D arquitectónica realista (SVG, CSS y estados).
- **`presencia.py` / `camara.py`**: Presencia y seguimiento facial con MediaPipe.
- **`prueba_humo.py`**: Suite de validación rápida de sintaxis, reglas de 15 KB y módulos clave.

### Reglas de oro de desarrollo
1. **Tamaño máximo:** Ningún archivo de código debe superar los **15 KB** (~15,360 bytes). Si crece, dividir en módulos especializados.
2. **Hilo principal Qt protegido:** Cero llamadas a Qt desde hilos secundarios. Toda comunicación hacia la interfaz va por `app.cola` o señales.
3. **I/O en hilos secundarios:** Red, APIs de LLM, TTS y operaciones pesadas siempre corren en hilos `threading.Thread(daemon=True)`.
4. **Acciones:** Toda nueva capacidad del asistente se expone mediante `acciones.registrar(nombre, funcion, descripcion)`.
5. **Configuración y claves:** Exclusivamente en `config.py` (ignorado en git). Plantilla pública en `config.example.py`.

## 4. Estado actual (lo que ya funciona)
- Rostro animado reactivo con mirada suave (`camara.py`), microexpresiones y parpadeo natural.
- Interrupción por voz (barge-in): corte instantáneo (<500ms) al decir "espera", "ya", "para", con filtro de eco.
- Síntesis en streaming por oraciones completas (`cerebro_parser.py`) sin cortes en conectores.
- Filtro estricto de alucinaciones de Whisper y descarte con log explícito (`oido.py`).
- Saludo inicial contextual en el arranque seguro para el hilo Qt (`nacimiento.py`, `eventos.py`).
- Prompt compacto (<1350 tokens) con inyección selectiva precisa (`cerebro_categorias.py`) y suite en `prueba_humo.py`.
- Voz panameña natural con `voz_reproductor.py` thread-safe (RLock, buffers vivos, RMS labial y barge-in <500ms).
- Reconocimiento con Whisper (VAD adaptativo 0.45s con caída de energía, prompt contextual) y respaldo Vosk.
- Latencia: caché de perfil en RAM (<1ms), Groq ultra-rápido y muletillas inactivas por defecto.
- Aro facial reactivo: celeste en reposo y amarillo al escuchar.
- Audio thread-safe: exclusión mutua estricta de streams entre oido y palabra_clave (sin 0xc0000374).
- Bucle de falsos disparos erradicado (`PALABRAS_EXCLUIDAS` en `palabra_clave.py`).
- Enrutamiento inteligente a múltiples LLM con fallback, pool Keep-Alive y enfriamiento 429 exacto.
- Memoria duradera con fechas, categorías y filtro de privacidad.
- Acciones por voz: recuerdos, recordatorios persistentes, proveedores y control de escucha.
- Control de laptop por niveles: libre (apps/sitios, volumen, música inmediata y ducking), peligroso exclusivo por Telegram (apagar, reiniciar con código local y verificación `ID_TELEGRAM_DUENO`) y prohibido con auditoría.
- Modo reposo, panel para tablet y casa virtual 2D interactiva (`/casa`, toque de anillo y movimiento táctil).
- Suite de prueba de humo (`prueba_humo.py`) y arquitectura modular (todos los archivos <= 15 KB).

## 5. Tareas pendientes y pospuestas
- [ ] **Rotar clave de Groq:** Clave expuesta en el pasado; cambiarla en `config.py` y consola de Groq.
- [ ] **Cerebro premium ($5/mes):** Integrar proveedor de alta calidad con límite estricto de gasto como opción alternativa.
- [ ] **Respaldo local:** Modelo SLM/LLM cuantizado local (Ollama / llama.cpp) para operar 100% offline.
- [ ] **Iniciativa propia:** Saludos o comentarios espontáneos en momentos adecuados sin esperar turno.
- [ ] **Núcleo headless y nube:** Separar lógica para correr 24/7 en VPS conectada al bot de Telegram.
- [ ] **Respaldos fuera de Git:** Script para respaldar `memoria.json`, audios y config en carpeta segura.
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
