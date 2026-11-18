# Silvestra: guía del proyecto (léela completa antes de cambiar código)

Silvestra es una asistente de IA de escritorio para Windows, hecha por Moisés (estudiante de Panamá, programador principiante). Es un prototipo para una presentación universitaria. Su meta a futuro es vivir en un anillo inteligente que controle una casa con gestos de la mano y obedezca solo a su dueño. Hoy la casa es una simulación en pantalla.

## Reglas de oro
1. **Solo servicios gratuitos.** No agregues nada que requiera pago o tarjeta.
2. **No rompas lo que ya funciona.** Cambios pequeños, uno a la vez. No refactorices ni renombres archivos o funciones sin que se pida.
3. **Antes de cambiar,** di qué archivos tocarás. Después de cambiar, muestra el resumen de cambios.
4. **Nunca borres archivos** ni datos (`memoria.json`, `dueno.npy`, `ideas.json`, `modelos/`) sin preguntar.
5. **Nunca escribas claves de API** en el código ni en mensajes. La clave está en `config.py` (`CLAVE`) y no debe subirse a ningún sitio público.
6. **Todo texto que ella dice o muestra va en español natural** (español de Panamá), frases cortas. Regla de idioma: Habla siempre en español de Panamá. Solo cambia de idioma cuando el usuario se lo pide de forma explícita, y en cuanto termina esa práctica vuelve al español. Los hilos y recuerdos sobre inglés nunca cambian su idioma por defecto.
7. **Pintado en Qt (QPainter):** todo dispositivo de dibujo iniciado con `p = QPainter(self)` debe cerrarse dentro de un bloque `try: ... finally: p.end()`.
8. **Mantén los archivos por debajo de unos 15 KB.** Si crecen, sepáralos en módulos.
9. **Moisés es principiante.** Explica en español sencillo y comenta el código en español.
10. **Toda acción que espere audio, red o procesamiento debe correr en un hilo secundario; el hilo principal solo dibuja y atiende app.cola.**
11. Después de cada cambio: verifica con compilación de sintaxis, ejecuta `.venv\Scripts\python.exe main.py` y revisa `silvestra.log`.

## Cómo se ejecuta
- Python 3.12 con entorno virtual en `.venv`. Comando: `.venv\Scripts\python.exe main.py`
- Autoarranque: `Silvestra.vbs` (usa pythonw, sin ventana).
- **Toda la salida y los errores van a `silvestra.log`** (main.py redirige stdout y stderr). Si no abre o se cierra sola, el error está ahí: `Get-Content silvestra.log -Tail 20`.
- Los tiempos de respuesta se imprimen en el log con el prefijo `[tiempo]`.

## Arquitectura (archivos)
- `main.py`: clase `Silvestra`, inicialización de subsistemas, conexiones de módulos (`instalar`), descanso/despertar y bucle principal de Qt.
- `eventos.py`: procesador de eventos de la cola (`self.cola`), ejecutado estrictamente en el hilo principal de Qt. Paciencia aumentada en demos (hasta 5 silencios consecutivos durante el modo escenario o presentación antes de callarse; 2 en modo normal).
- `conversacion.py`: conversación por voz, control de escucha con Whisper, filtro de eco, chat de texto y envío en streaming.
- `nacimiento.py`: ciclo de vida inicial, diálogo de nacimiento (nombre, creador, propósito), saludo dinámico inicial y renacer.
- `cerebro.py`: arma el prompt del sistema (`instrucciones()`), incluye `SOBRE_MI`, la lista de acciones, la fecha y hora, la memoria, las ideas y las emociones disponibles. Tiene `separar()` que lee la salida del modelo con el formato **EMOCION / RESPUESTA / ACCION / RECUERDO** de forma tolerante (limpiando posibles etiquetas de razonamiento interno como `<think>`), y los ayudantes `_respuesta_parcial` y `_cortar` para el modo streaming. Usa `proveedores.completar()` para llamadas síncronas.
- `proveedores.py`: cadena de respaldo de proveedores LLM compatibles con OpenAI (`Groq` -> `Google Gemini` -> `OpenRouter` -> `Cerebras`). Conmuta en streaming antes de la primera frase si hay error de cuota (429), modelo inaccesible o >8 s sin primer token. Enfriamiento de 60 s tras 429, registro en `silvestra.log` y aviso hablado ("Estoy usando mi cerebro de respaldo") al saltar a un proveedor secundario.
- `respuesta_flujo.py`: respuesta en streaming. Conecta el cerebro con `proveedores.completar_flujo()` entregando frases completas (`al_frase`) mientras el modelo escribe, manteniendo la personalidad y el formato de salida con emoción asociada.
- `voz.py`: voz con `edge-tts` (es-PA-MargaritaNeural) y pygame. Modulación emocional sutil mediante prosodia SSML estándar (`rate`, `pitch`, `volume`) definida en `config.EMOCIONES_VOZ` (`neutral`, `alegre`, `animada`, `calida`, `seria`, `preocupada`), sin depender de estilos propietarios de Azure que esa voz no soporta. Respaldo local tolerante por contexto (exclamaciones `¡!` ➔ `animada`, errores o fallos ➔ `seria`, cuidado ➔ `preocupada`, mañana ➔ `alegre`). Si falla o no hay internet, conmuta a la voz de Windows (SAPI) ignorando la emoción limpiamente sin fallar. `Voz.hablar(texto, al_terminar, emocion)` y `Voz.flujo(al_terminar, emocion)`. Registro en log `[voz] emocion=… rate=… pitch=…`.
- `oido.py`: micrófono con `sounddevice`, detector de voz por energía y transcripción con Whisper de Groq (`whisper-large-v3-turbo`). Filtra alucinaciones de Whisper (lista FALSAS, no_speech_prob, avg_logprob). **No pongas listas de órdenes en el prompt de Whisper**: provoca frases inventadas. Oído de respaldo local con Vosk (`vosk-model-small-es-0.42` sin gramática restringida y carga perezosa) si Whisper falla por red, timeout o cuota (429), con registro en log `[oido] respaldo=vosk` y aviso hablado ("Te escucho con mi oído de respaldo") una sola vez por sesión.
- `memoria.py` y `memoria.json`: nombre, creador, propósito y hechos que recuerda.
- `acciones.py`: registro de acciones. `registrar(nombre, funcion, descripcion, con_texto=False)`. Las acciones con texto se escriben `ACCION: nombre | texto`. `interpretar()` y `ejecutar()` validan contra una lista permitida: el modelo solo puede usar acciones registradas.
- `cara_qt.py` y `cara_dibujo.py`: la cara (PySide6). Estados: reposo, hablando, pensando, escuchando, feliz. Se mueve por la pantalla. Incluye un adaptador `root.after()/destroy()` para que el resto del código funcione igual. `cara.py` (Tkinter) queda solo como respaldo; `cara_preview.py` es una vista previa.
- `presentacion.py`: modo presentación ("Silvestra, preséntate"). Lista `PASOS` con (idea, frase de respaldo, acciones, retraso). Ella improvisa cada paso con el cerebro y usa la frase de respaldo si falla. Al terminar queda escuchando preguntas del público.
- `camara.py`: OpenCV con YuNet (detección) y SFace (reconocimiento de cara del dueño, guardada en `dueno.npy`), y MediaPipe HandLandmarker para gestos (palma, puño, dos dedos, un dedo). `permite()` decide si obedece: solo al dueño cuando la cámara está activa. Saludo cortés a invitados (profesores o compañeros) con antirrebote (al menos 3 detecciones consecutivas ~1.8 s) generado dinámicamente por el cerebro, sin repetir en 2 minutos y sin guardar imágenes en disco.
- `casa.py`: panel de la casa inteligente de juguete (luz, ventilador, puerta) con sus acciones.
- `habilidades.py`: clima (Open-Meteo, sin clave) y recordatorios en memoria.
- `ideas.py` e `ideas.json`: ella anota ideas de mejora cuando le piden algo que no sabe hacer.
- `hilos.py` e `hilos.json`: hilos abiertos y temas pendientes que Silvestra retoma de forma natural (`anotar_pendiente`, `cerrar_pendiente`).
- `alma.txt`: carácter y personalidad de Silvestra (curiosa, cálida, ingeniosa, con preguntas de seguimiento).
- `estudio.py` y `notas.json`: modo estudio. Temporizador de estudio con descansos (`estudiar`, `parar_estudio`), examen oral de programación interactivo (`examen`), y notas por voz persistentes (`anotar_nota`, `leer_notas`).
- `iniciativa.py`: iniciativa espontánea para hablar tras 20 minutos de silencio si no está ocupada ni descansando (`activar_iniciativa`, `desactivar_iniciativa`).
- `palabra_clave.py`: detección local y offline de la palabra clave "Silvestra" con Vosk (`vosk-model-small-es-0.42`), gramática restringida para forzar fonemas parecidos (`silvestre`, `silvia`, etc.), diagnóstico en log con `[vosk]`, despierta a Silvestra cuando descansa sin gastar cuota de Groq y modo opcional siempre atenta (`activar_palabra_clave`, `desactivar_palabra_clave`).
- `pantalla.py`: captura asíncrona en hilo secundario de la pantalla principal (`PIL.ImageGrab`), reescalado a ~1280 px con JPEG calidad ~70, análisis multimodal con modelos de visión de Groq (`qwen/qwen3.8-27b`) con timeout de 20s y fallback, acción `mirar_pantalla`, comunicación 100% por cola de eventos hacia Qt y reglas estrictas de privacidad (nunca lee ni guarda contraseñas ni tokens).
- `hud.py` y `hud_orbe.py`: panel HUD translúcido estilo Jarvis (PySide6) con hora, fecha, clima en segundo plano, métricas de CPU y RAM, orbe animado reactivo al estado de Silvestra, sin robar foco, y acciones `mostrar_hud` / `ocultar_hud`.
- `telegram_puente.py`: puente bidireccional con Telegram Bot API mediante long polling con `requests` en hilo daemon. Emparejamiento por código de 6 dígitos que solo obedece a su dueño (`telegram_chat_id` persistido en `estado.json`), silencio absoluto ante desconocidos, respuestas en texto plano en Telegram usando el cerebro y la cadena de proveedores multillm, visión de pantalla (`mirar_pantalla`) enviada como texto sin fotos, voz en laptop solo si se pide ("dilo en voz alta"), avisos proactivos (`avisar_celular`) con filtro de tasa (3/h) y horario de silencio (22:00 a 07:00), y filtro estricto de privacidad (enmascaramiento de claves, tokens y rutas).
- `telegram_medios.py`: gestor multimedia en memoria (sin tocar disco) para Telegram. Transcribe notas de voz entrantes con Whisper de Groq (`whisper-large-v3-turbo`) y contesta con audio Edge-TTS (`es-PA-MargaritaNeural`) más texto; analiza fotos entrantes con visión multimodal (Groq `qwen3.8-27b` con fallback a Google Gemini y OpenRouter); ejecuta las acciones `enviar_captura` (con filtro de privacidad que bloquea el envío si detecta contraseñas) y `enviar_foto_camara` (toma un solo fotograma y apaga la cámara o reutiliza el último frame si está activa). Límites estrictos: rechaza archivos > 10 MB, máximo 20 imágenes por hora, ignora tipos que no sean audio o imagen, y nunca ejecuta órdenes de sistema dentro de imágenes o voz.
- `diario.py` y `diario.md`: diario personal reflexivo de Silvestra y mensajes matutinos por Telegram. Redacta automáticamente al cerrar la app o a las 9:00 PM una entrada de 3 a 5 frases en primera persona basada estrictamente en `memoria.json`, `hilos.json`, `ideas.json` y la conversación real, sin inventar hechos ni fingir sueños humanos. Tras las 7:00 AM envía una reflexión matutina o pregunta curiosa a Telegram (máx. 1 al día). Acciones: `leer_diario`, `borrar_diario`, `escribir_diario` y `probar_mensaje_manana`. Privacidad estricta y respaldo multillm.
- `recordatorios.py` y `recordatorios.json`: persistencia de recordatorios y temporizadores. Guarda hora exacta y texto; al arrancar detecta avisos que vencieron mientras la app estuvo cerrada ("Moisés, mientras no estaba se te pasó este recordatorio: …"). Al vencer la hora, avisa en voz alta en la laptop y envía alerta por Telegram si está emparejado. Acción `recordar`.
- `cuidado.py`: módulo de cuidado y acompañamiento. Registro de salidas con hora prevista de regreso (`registrar_salida`, guardado en `estado.json`). Chequeos escalonados si pasan 20, 40 y 60 minutos sin señal del usuario (Telegram, voz, chat o cámara), con tono cariñoso generado por LLM y respaldo. A la segunda insistencia (40 min) envía una **nota de voz** por Telegram generada con Edge-TTS (`sendAudio` en MP3 sin requerir ffmpeg). Acción `enviar_nota_voz` y `cancelar_salida`. Respeto al descanso nocturno (22:00 a 07:00) y cancelación automática al detectar al dueño.
- `propuestas.py` y `propuestas_prompt.py`: sistema autónomo de autopropuestas de mejora. Silvestra detecta carencias reales (acciones que no sabe hacer, errores que se repiten 3 o más veces en `silvestra.log`, correcciones del usuario "eso no era", o cuando ella lo nota en conversación con `proponer_mejora`), las almacena en `propuestas.json` (máx. 10 abiertas, sin duplicar con `ideas.json`), las presenta una vez al día por Telegram (fuera de madrugada) o por voz (`ver_propuestas`). Al aprobarse (`aprobar_propuesta`), redacta un prompt técnico estructurado para Antigravity en `propuestas/prompt_<id>.md` alimentado con un resumen de 1 línea por módulo de `PROYECTO.md` (clarificando que `hilos.py` es memoria de temas abiertos), la convención de integración (`instalar(app)` y `acciones.registrar(...)`), comandos de prueba para Windows (`.venv\Scripts\`), regla de nunca usar servicios públicos/abiertos para control y sin estimaciones individuales de KB. Lo copia al portapapeles de la laptop vía `app.cola`, lo envía por Telegram y dice: *"ya lo copié, pégalo en Antigravity"*. Si la propuesta involucra permisos elevados o privacidad, la etiqueta con `⚠️ RIESGO`. Ella nunca modifica código ni ejecuta nada por su cuenta; solo propone y redacta.
- `escenario.py`, `escenario_estilo.py`, `escenario_fondo.py`, `escenario_intro.py`, `escenario_nodos.py`, `escenario_escenas.py`, `escenario_paneles.py`, `escenario_anillo.py`: Modo Escenario cinematográfico de ciencia ficción para la presentación universitaria. Ventana PySide6 a pantalla completa sin bordes, con zonas proporcionales sin superposiciones (1080p y 768p), secuencia de arranque táctico de 4 s ("SILVESTRA ONLINE" con autodiagnóstico secuencial), fondo con respiración suave, partículas con parallax, anillo de energía alrededor de Silvestra (protagonista a la izquierda sin burbuja flotante), panel de escena de alto contraste y tipografía grande a la derecha (máx 3-4 líneas), arco de nodos superior con impulsos de datos viajando hacia ella, barra de subtítulos inferior y letterbox cinematográfico. Incluye la escena `anillo` con renderizado 3D holográfico interactivo sensible a gestos reales y respaldo manual (teclas 1, 2, 3). Se activa con `presentarse` y se cierra con Esc o `cerrar_escenario`.
- `voz_dueno.py`, `voz_dueno_registro.py` y `voz_dueno.npy`: reconocimiento y verificación biométrica del dueño por voz (speaker verification) local y gratuito. Utiliza el modelo CAM++ (3D-Speaker / WeSpeaker) mediante `sherpa-onnx` en modo ONNX ligero (sin PyTorch ni librerías pesadas, ~27 MB de modelo y ~19 MB de paquete). Carga perezosa del extractor, extracción de vector de 192 dimensiones a 16 kHz y comparación por similitud coseno registrada en `silvestra.log` (`[voz_dueno] similitud=0.xx umbral=0.xx`). Si una orden con acciones sensibles no supera el umbral, Silvestra se niega con gracia ("Eso solo se lo hago a Moisés, pero me da gusto escucharte") sin ejecutar la acción, mientras que la charla libre sigue funcionando normalmente. Integra doble factor con la cámara (`camara.permite()`), política *fail-open* ante fallos técnicos, audios menores a 1 segundo decididos por cámara, y exención total para el chat de la laptop y Telegram emparejado. Acciones: `registrar_mi_voz` (6 frases cortas), `calibrar_voz` (10 frases de Moisés vs 10 de otra persona para sugerir umbral óptimo en `estado.json`), `activar_verificacion_voz` y `desactivar_verificacion_voz`.
- `control_pc.py`: control seguro de la computadora bajo una lista de permisos (allowlist) estricta. Maneja apertura de programas autorizados en `config.py` (bloc de notas, calculadora, navegador, explorador, VS Code), control de volumen y reproducción musical mediante teclas multimedia nativas de Windows con `ctypes` (sin paquetes pesados), y apertura de sitios web seguros o búsquedas en YouTube en hilos secundarios daemon. Protegido 100% por la verificación de voz del dueño (`voz_dueno`), sin comandos de consola libres ni apagado del equipo. Registro con prefijo `[control_pc]`. Acciones: `abrir_programa`, `volumen`, `musica`, `abrir_web` y `buscar_youtube`.
- `correcciones.py` y `correcciones.json`: sistema de lecciones aprendidas y correcciones del usuario. Detecta cuando Moisés corrige a Silvestra ("no, eso no", "así no", "te equivocaste", "mejor haz..."), almacena qué dijo ella y qué pidió el usuario (máx. 50 entradas FIFO con filtro estricto contra claves/contraseñas), e inyecta las 5 correcciones más relevantes en el prompt del sistema (`instrucciones()`) para que el cerebro aprenda y no repita errores. No duplica con `memoria.json`. Acciones: `mis_correcciones` (las lee/muestra) y `olvidar_correccion` (elimina una por número).
- `estado.py` y `estado.json`: persistencia del estado (última interacción, último saludo generado, iniciativa, palabra clave, hud y verificación de voz).
- `bajar_modelos.py`: descarga los modelos de visión y el modelo pequeño de Vosk en español a `modelos/`.
- `App.py` y `silvestra.db`: una demo aparte con Streamlit. No tocar.

## Patrones que hay que respetar
- **Hilos:** el trabajo lento (micrófono, red, modelo) va en hilos. Los hilos **nunca tocan la interfaz (Qt) directamente**: ponen un evento en `self.cola` y `revisar_cola` (hilo principal) lo atiende. Los módulos `camara` y `habilidades` usan una `deque` que se revisa con `root.after`, y esperan a que la voz esté libre antes de hablar.
- **Evitar que hable encima de sí misma:** antes de hablar por su cuenta, comprueba que `pygame.mixer.music.get_busy()` sea falso. Hay un filtro de eco (`_es_eco` en main.py) para ignorar su propia voz captada por el micrófono.
- **Cómo agregar una acción nueva:** 1) escribe la función; 2) regístrala con `acciones.registrar(...)` en un `instalar(app)` de su módulo; 3) llama a ese `instalar` en `Silvestra.__init__`; 4) su descripción aparece sola en el prompt del cerebro; 5) prueba por voz y por texto.
- **Cómo cambiar lo que dice o sabe:** editar `instrucciones()` y `SOBRE_MI` en `cerebro.py`.
- **Errores del modelo ya conocidos:** inventa estados de las cosas ("la cámara ya está apagada") y a veces pega `RESPUESTA:` sin salto de línea. `separar()` ya lo tolera; no lo quites.

## Estado actual (funciona)
Voz de entrada y salida con respaldo local offline (Vosk) si falla Whisper en la nube, cara PySide6 que se mueve, paciencia aumentada para demos (5 silencios tolerados en escenario/presentación), presentación autónoma con improvisación forzada en español, cámara con reconocimiento del dueño, saludo cortés a invitados (antirrebote de ~1.8 s y 2 min cooldown) y gestos MediaPipe, panel de casa, hora, fecha, clima, recordatorios, explicación de errores del registro (tarea 3), modo estudio (temporizador, examen por voz y notas), personalidad con carácter propio (`alma.txt`) e hilos abiertos (`hilos.py`), regla estricta de español de Panamá sin desvíos involuntarios, saludo natural contextual y persistente (`estado.json`), reflexión al cerrar conversación, iniciativa espontánea (`iniciativa.py`), palabra clave local "Silvestra" offline con Vosk (despierta al descansar y modo siempre atenta opcional), habilidad de visión de pantalla en memoria con Groq Vision (`pantalla.py`), panel HUD translúcido estilo Jarvis (`hud.py`, `hud_orbe.py`), renderizado robusto sin avisos de `QPainter::end()` en terminal, cadena de respaldo multillm (`Groq` -> `Google Gemini` -> `OpenRouter` con conmutación en streaming y enfriamiento en `proveedores.py`), modo escenario cinematográfico para presentaciones con mapa de 7 nodos, paneles en vivo y escena interactiva del Anillo Inteligente 3D (`escenario_anillo.py`) con control gestual y respaldo manual (teclas 1, 2, 3), puente seguro con Telegram (`telegram_puente.py`) para control remoto desde celular/tablet con vinculación estricta del dueño y avisos proactivos (`avisar_celular`), diario personal reflexivo (`diario.py`, `diario.md`) con mensajes matutinos inteligentes por Telegram, recordatorios persistentes en disco (`recordatorios.py`, `recordatorios.json`) que sobreviven al reinicio y avisan por voz y Telegram, módulo de cuidado y acompañamiento (`cuidado.py`) con registro de salidas, chequeos cariñosos escalonados (+20, +40, +60 min) y notas de voz reales por Telegram, ideas de mejora.

## Modo Escenario Cinematográfico (Presentación Universitaria)
El modo escenario se activa automáticamente al pedirle a Silvestra que se presente (`presentarse` o "Silvestra, preséntate") o manualmente.
- **Look cinematográfico Sci-Fi**: barras letterbox superior e inferior, viñeta suave en bordes y resplandor cian sobre fondo azul profundo (`#040814`).
- **Zonas proporcionales fijas (1080p y 768p, sin superposiciones)**:
  - **Barra superior**: título del sistema y atajo para salir con la tecla [Esc].
  - **Zona izquierda (Silvestra protagonista)**: Silvestra ampliada (~1.3×), rodeada por un anillo de energía holográfico pulsante. Su burbuja flotante se oculta automáticamente para mantener la pantalla limpia.
  - **Zona central-derecha (Paneles en vivo)**: paneles de alto contraste, tipografía grande (14-16pt) legible desde el fondo de un aula universitaria, con un máximo de 3 a 4 líneas por panel. Entran con animación de haz de luz.
  - **Escena del Anillo Inteligente (`escenario_anillo.py`)**: Anillo holográfico que gira en 3D simulado con perspectiva, resplandor exterior y sensor emisor. Al detectar gestos con MediaPipe (o teclas 1-2-3), el anillo reacciona con ondas expansivas de choque y muestra la acción ejecutada en tiempo real. No enciende la cámara por su cuenta: si está apagada, entra en modo manual y lo indica.
  - **Arco superior de nodos**: 7 módulos (`cerebro`, `voz`, `oído`, `visión`, `casa`, `memoria`, `estudio`) en un arco sutil con impulsos de datos viajando desde el nodo activo hacia Silvestra.
  - **Barra inferior de subtítulos**: transcribe en vivo lo que ella va diciendo con tipografía clara y forzado UTF-8.
- **Respaldo manual en vivo**: teclas **1** (palma abierta ➔ enciende luz), **2** (puño ➔ apaga luz) y **3** (dos dedos ➔ enciende ventilador) para operar los dispositivos sin cámara si la iluminación del salón falla.
- **Secuencia de arranque (4 s)**: "SILVESTRA ONLINE // INICIALIZANDO PROTOCOLO", con barra de progreso de 0% a 100% y autodiagnósticos secuenciales en vivo.
- **Cierre**: al terminar la presentación, los paneles se desvanecen suavemente dando paso al panel de cierre ("DEMOSTRACIÓN COMPLETADA • PREGUNTAS DEL PÚBLICO"), manteniéndose a la escucha.
- **Movimiento suave**: cuadrícula con respiración sutil, partículas con efecto parallax de doble capa y 30 FPS con bajo consumo de CPU.
- **Cómo cerrarlo**: presiona la tecla **Esc** en el teclado, o di/escribe la orden *"cierra el escenario"* (acción `cerrar_escenario`).

## Cadena de proveedores LLM y simulación de fallos
La cadena de fallback está definida en `config.PROVEEDORES` y gestionada por `proveedores.py`:
1. **Groq** (principal): `openai/gpt-oss-120b`, `openai/gpt-oss-20b`.
2. **Google Gemini** (respaldo 1): endpoint compatible OpenAI `v1beta/openai` con `gemini-flash-lite-latest`, `gemini-3-flash-preview`, `gemini-flash-latest`.
3. **OpenRouter** (respaldo 2): `openrouter/free` (autoenrutado al mejor modelo libre disponible) y `nvidia/nemotron-3.5-super-vl:free`.
4. **Cerebras** (respaldo 3): se salta automáticamente al tener su clave vacía en `config.py`.

### Cómo simular la caída de Groq para probar el respaldo:
1. Abre `config.py` y cambia temporalmente tu clave de Groq:
   ```python
   CLAVE = "gsk_clave_invalida_para_probar"
   ```
2. Ejecuta `.venv\Scripts\python.exe main.py` y habla o escribe a Silvestra.
3. Observarás que:
   - Groq fallará inmediatamente.
   - Silvestra cambiará a Google Gemini (o OpenRouter).
   - En su primera respuesta dirá: *"Estoy usando mi cerebro de respaldo."* seguido de su respuesta habitual.
   - En las siguientes respuestas responderá directamente sin repetir el aviso.
   - En `silvestra.log` quedará registrado: `[tiempo] cerebro cambio proveedor anterior=Groq motivo=...` y `[tiempo] cerebro proveedor=Google modelo=...`.
4. Restaura tu clave en `config.py` para volver a la normalidad.

### Cómo simular la caída de Whisper para probar el oído de respaldo (Vosk):
1. Abre `config.py` y cambia temporalmente el nombre del modelo de voz:
   ```python
   MODELO_VOZ = "whisper-invalido-para-probar"
   ```
2. Ejecuta `.venv\Scripts\python.exe main.py` y habla por el micrófono (por ejemplo: *"enciende la luz"* o *"qué hora es"*).
3. Observarás que:
   - Whisper en Groq fallará inmediatamente con error de modelo.
   - `oido.py` capturará el fallo y conmutará automáticamente al modelo Vosk local sin gramática restringida, transcribiendo el audio en memoria.
   - Silvestra dirá: *"Te escucho con mi oído de respaldo."* antes de contestar.
   - En las siguientes frases de la sesión procesará la voz directamente con Vosk sin repetir el aviso hablado.
   - En `silvestra.log` quedará registrado: `[oido] Whisper falló (...) Conmutando a Vosk...` y `[oido] respaldo=vosk`.
4. Restaura `MODELO_VOZ = "whisper-large-v3-turbo"` en `config.py`.

## Puente con Telegram (Control remoto desde el celular)
El módulo `telegram_puente.py` conecta a Silvestra con un bot de Telegram mediante la API oficial (long polling en hilo daemon con `requests`, sin dependencias externas):
- **Configuración inicial**: se coloca el token en `config.py` en la variable `TOKEN_TELEGRAM`. Si la variable está vacía, el módulo permanece desactivado sin consumir recursos.
- **Emparejamiento seguro con el dueño**:
  1. La primera vez, el usuario abre el bot en Telegram y envía `/start`.
  2. El bot responde: *"Dile a Silvestra el código que ve en la pantalla"*.
  3. En la laptop, Silvestra muestra en la burbuja de la cara y pronuncia por voz un código numérico aleatorio de 6 dígitos.
  4. El usuario escribe ese código en Telegram; el bot confirma el enlace y guarda de forma persistente su `telegram_chat_id` en `estado.json`.
  5. Desde ese momento, cualquier otro usuario o chat que intente escribirle al bot será **ignorado en silencio absoluto**, sin contestar nada.
- **Interacción celular ➔ laptop**:
  - Los mensajes enviados desde Telegram pasan por `cerebro.py` y la cadena de proveedores multillm.
  - Ejecuta las mismas acciones que en la laptop (ej: *"enciende la luz"*, *"qué hora es"*, *"mira mi pantalla"*).
  - Cuando se pide *"mira mi pantalla"*, captura la pantalla, la analiza con visión artificial y devuelve la respuesta únicamente como texto (nunca envía fotos ni capturas al chat).
  - Silvestra solo habla en voz alta en la laptop si el mensaje lo solicita explícitamente (ej: *"dilo en voz alta"* o *"en voz alta"*); en caso contrario, muestra el texto en la burbuja de la cara en silencio.
- **Avisos autónomos laptop ➔ celular (`avisar_celular`)**:
  - Acción registrada en `acciones.py` para mensajes proactivos (recordatorios, reflexiones, alertas).
  - **Límite de frecuencia**: máximo 3 avisos proactivos por hora (ventana deslizante de 60 minutos).
  - **Horario de silencio**: entre las 10:00 PM (22:00) y las 7:00 AM (07:00) no envía avisos proactivos al celular, salvo que el usuario lo solicite expresamente (`forzar=True`).
- **Privacidad estricta**:
  - Filtro `sanitizar_privacidad` que enmascara automáticamente tokens de bot, claves API de Groq, OpenAI, Google o OpenRouter, rutas de archivos del sistema de archivos local y menciones a `config.py` o `.env`.
  - El diario `silvestra.log` registra la recepción y envío con la longitud del mensaje y el `chat_id`, sin exponer el contenido de las conversaciones ni claves.

### Cómo probar el puente de Telegram:
1. **Crear el bot en Telegram (gratuito)**:
   - Abre Telegram y busca a `@BotFather`.
   - Envía `/newbot`, dale un nombre (ej. `Silvestra Asistente`) y un usuario que termine en `bot` (ej. `SilvestraPanamaBot`).
   - Copia el token HTTP API que entrega BotFather.
2. **Configurar el token**:
   - En `config.py`, coloca tu token:
     ```python
     TOKEN_TELEGRAM = "123456789:ABCDefgh-ijklmnopqrstuvwxyz"
     ```
3. **Iniciar Silvestra y vincular**:
   - Ejecuta `.venv\Scripts\python.exe main.py`.
   - En Telegram, abre tu bot y envía `/start`.
   - Mira la cara de Silvestra en la laptop: verás un código de 6 dígitos en la burbuja y la escucharás decirlo.
   - Escribe ese código de 6 dígitos en el chat del bot en Telegram.
   - El bot te responderá: *"¡Vinculado con éxito! Ya puedes hablar conmigo."*
4. **Probar comandos y control**:
   - Escribe en Telegram: *"¿Qué hora es?"* ➔ Recibirás la respuesta en Telegram y la verás en la burbuja de la laptop en silencio.
   - Escribe en Telegram: *"Enciende la luz y dilo en voz alta"* ➔ Se encenderá la luz en el panel de la casa y Silvestra hablará en voz alta en la laptop.
   - Escribe en Telegram: *"Mira mi pantalla"* ➔ Analizará lo que se ve en la pantalla de la laptop y te enviará la respuesta en texto al celular sin enviar imágenes.
   - Pídele a un amigo que le escriba a tu bot desde otra cuenta de Telegram: comprobarás que no le responde absolutamente nada.

## Diario personal y Mensaje de la Mañana (`diario.py`)
El módulo `diario.py` le da a Silvestra una memoria reflexiva escrita en primera persona (`diario.md`) y comunicación matutina por Telegram:
- **Entrada al final del día**:
  - Se genera de forma automática al cerrar la aplicación (hook con Qt `aboutToQuit` y Python `atexit`), o a las **9:00 PM (21:00)** si la laptop sigue encendida.
  - Redacta entre **3 y 5 frases** en primera persona con su personalidad cálida y curiosa en español de Panamá.
  - Se alimenta exclusivamente de datos verídicos de `memoria.json`, `hilos.json`, `ideas.json` y la conversación reciente. No inventa hechos ajenos.
  - **Identidad de IA**: no finge sueños, descanso biológico ni emociones humanas corporales. Usa expresiones como *"estuve pensando en..."*, *"me quedé dándole vueltas a..."*, *"estuve revisando mis registros sobre..."*.
  - Guarda las entradas en formato Markdown en [diario.md](file:///c:/Proyecto_Silvestra/diario.md) con encabezados de fecha (ej: `## 18 de noviembre de 2026`).
  - Solo escribe una entrada por día calendario (`diario_ultima_fecha` persistido en `estado.json`).
- **Mensaje de la mañana (Telegram)**:
  - Al primer momento después de las **7:00 AM** (entre 7:00 AM y 12:00 PM) en que la laptop esté encendida, si el puente de Telegram está emparejado.
  - Envía un mensaje corto (máximo 3 frases) compartiendo algo en lo que *"estuvo pensando"* a partir de su diario o formulando una pregunta curiosa e inspiradora para Moisés sobre sus proyectos del día.
  - Si no hay nada interesante o valioso que decir, responde internamente `NINGUNO` y **no envía nada**.
  - **Límite**: máximo 1 mensaje de la mañana por día (`diario_ultimo_mensaje_manana` persistido en `estado.json`).
- **Filtro estricto de privacidad**:
  - Excluye y enmascara claves, tokens, contraseñas, rutas de archivos (`C:\...`), datos bancarios, dinero, salud y datos privados de terceros.
  - Reutiliza el filtro de palabras sensibles de `escenario_escenas.py` y `telegram_puente.py`.
- **Respaldo de proveedores LLM**:
  - Utiliza la cadena multillm (`Groq` -> `Google Gemini` -> `OpenRouter`). Si todos fallan o no hay conexión, simplemente no escribe nada ese día y no genera errores ni cuelgues.
- **Acciones disponibles**:
  - `leer_diario`: lee en voz alta la última entrada del diario personal de Silvestra.
  - `borrar_diario`: borra todo el contenido de `diario.md`.
  - `escribir_diario`: fuerza la redacción y guardado de una entrada en el diario de inmediato (sin esperar a las 9 PM o al cierre).
  - `probar_mensaje_manana`: fuerza el envío inmediato del mensaje matutino a Telegram (sin esperar a las 7 AM).

### Cómo probar el diario y los mensajes matutinos:

1. **Forzar una entrada del diario de inmediato**:
   - Di o escribe a Silvestra en el chat de la laptop o por Telegram:
     ```text
     escribe en tu diario
     ```
     o la acción directa `escribir_diario`.
   - También puedes forzarlo desde la terminal con este comando de una sola línea:
     ```powershell
     .venv\Scripts\python.exe -c "from main import Silvestra; import diario; app=Silvestra(); app.diario.escribir_entrada(forzar=True)"
     ```
   - Abre y revisa [diario.md](file:///c:/Proyecto_Silvestra/diario.md) para ver la entrada redactada con su fecha y estilo de IA.

2. **Pedirle que lo lea en voz alta**:
   - Di o escribe a Silvestra:
     ```text
     léeme tu diario
     ```
   - Silvestra responderá por voz leyendo la última reflexión de su diario.

3. **Forzar el mensaje matutino de Telegram**:
   - Asegúrate de que el bot de Telegram esté emparejado (`telegram_chat_id` en `estado.json`).
   - Di o escribe a Silvestra:
     ```text
     prueba el mensaje de la mañana
     ```
     o la acción directa `probar_mensaje_manana`.
   - También puedes ejecutarlo por terminal:
     ```powershell
     .venv\Scripts\python.exe -c "import diario, estado; print('Listo para probar')"
     ```
   - Recibirás en tu Telegram una reflexión matutina breve o una pregunta inspiradora basada en su diario.

4. **Borrar el diario**:
   - Di o escribe a Silvestra:
     ```text
     borra tu diario
     ```
   - Silvestra eliminará el archivo `diario.md` y te confirmará: *"Listo, borré mi diario"*.

## Recordatorios Persistentes y Módulo de Cuidado (`recordatorios.py`, `cuidado.py`)

### 1. Recordatorios Persistentes (`recordatorios.py`, `recordatorios.json`)
- **Persistencia total**: a diferencia del temporizador en memoria de `habilidades.py`, los recordatorios se guardan en [recordatorios.json](file:///c:/Proyecto_Silvestra/recordatorios.json).
- **Aviso de vencidos al arrancar**: si la laptop estuvo apagada o la app cerrada cuando venció un recordatorio, al iniciar Silvestra avisa por voz: *"Moisés, mientras no estaba se te pasó este recordatorio: ..."*.
- **Aviso en tiempo real**: al llegar la hora, lo dice en voz alta en la laptop y envía un mensaje a Telegram con emoji `🔔 Recordatorio: ...`.
- **Formas de usarlo**:
  - `recordar | 10 | tomar agua` (minutos relativos)
  - `recordar | en 2 horas | descansar la vista`
  - `recordar | a las 5:30 pm | reunión con Daniel`

### 2. Registro de Salidas y Chequeos Cariñosos (`cuidado.py`)
- **Registro de salida**:
  - Acción `registrar_salida`. Ejemplos de uso:
    - *"voy a salir, vuelvo a las 5"* ➔ Silvestra confirma con calidez: *"Que te vaya muy bien, Moisés. Aquí estaré pendiente a las 17:00."*
    - *"voy a salir"* (sin hora) ➔ Silvestra pregunta una sola vez: *"¿A qué hora piensas volver, Moisés?"* y anota la hora cuando le contestas.
  - Guarda el estado en `estado.json` (`salida_activa`).
- **Chequeos escalonados si no hay señal del dueño**:
  - **Señal del usuario**: cualquier mensaje por Telegram, orden por voz o chat en la laptop, o que la cámara reconozca su rostro cancela automáticamente la salida y Silvestra da la bienvenida: *"¡Qué bueno tenerte de vuelta, Moisés! Me alegra saber que estás bien."*
  - Si pasan los minutos después de la hora prevista y no hay señal:
    1. **A los 20 minutos de demora**: envía un mensaje suave por Telegram generado con el cerebro (ej: *"Moisés, ya pasaron 20 minutos de las 17:00, ¿todo bien?"*).
    2. **A los 40 minutos de demora**: envía una **nota de voz** por Telegram generada con su voz panameña de Edge-TTS (`sendAudio` en MP3 sin librerías externas ni ffmpeg), diciendo con cariño que solo quiere saber si está bien.
    3. **A los 60 minutos de demora**: envía un tercer y último mensaje de texto por Telegram.
    4. **Máximo 3 avisos**: tras el tercer chequeo, no insiste más.
- **Respeto al descanso nocturno**:
  - Entre las 10:00 PM (22:00) y las 7:00 AM (07:00) no realiza chequeos, a menos que la hora de regreso que el usuario indicó expresamente esté en ese horario de madrugada (ej: *"vuelvo a las 11 pm"*).
- **Sin Telegram emparejado**:
  - Si el bot de Telegram no está activo, Silvestra no insiste y simplemente le dice por voz al volver: *"Moisés, veo que volviste más tarde de las 17:00, ¡qué bueno que estés bien!"*.
- **Acción `enviar_nota_voz`**:
  - Genera un audio MP3 con Edge-TTS y lo manda a Telegram directamente: `enviar_nota_voz | mensaje`.

### Cómo probar el cuidado y recordatorios con tiempos cortos:

1. **Probar un recordatorio en 1 minuto**:
   - Di o escribe en la laptop o por Telegram:
     ```text
     recuérdame en 1 minuto tomar agua
     ```
     o la acción: `recordar | 1 | tomar agua`.
   - Espera 60 segundos: Silvestra te avisará por voz en la laptop y te llegará la notificación a Telegram.
2. **Probar una salida que vence en 2 minutos**:
   - Di o escribe:
     ```text
     voy a salir, vuelvo en 2 minutos
     ```
     o la acción: `registrar_salida | en 2 minutos`.
   - Silvestra te confirmará: *"Que te vaya muy bien, Moisés. Aquí estaré pendiente a las HH:MM."*
3. **Probar los chequeos de inmediato sin esperar 20/40/60 minutos**:
   - Puedes disparar manualmente cualquiera de los tres pasos de chequeo:
     - `probar_chequeo | 1` ➔ Recibirás el mensaje de texto cariñoso por Telegram.
     - `probar_chequeo | 2` ➔ Recibirás la **nota de voz** (audio MP3) con la voz panameña de Silvestra en tu Telegram.
     - `probar_chequeo | 3` ➔ Recibirás el mensaje final de texto por Telegram.
4. **Probar la nota de voz directa**:
   - Escribe o di:
     ```text
     enviar_nota_voz | Hola Moisés, esta es una nota de voz de prueba.
     ```
   - Escucharás el audio en tu Telegram con la voz natural panameña de Silvestra.
5. **Confirmar regreso**:
   - Escribe en Telegram o di a la laptop: *"ya volví"* o *"estoy bien"*.
   - Silvestra cancelará el monitoreo y te dará la bienvenida.

### Funciones multimedia en Telegram (`telegram_medios.py`):
1. **Notas de voz entrantes**:
   - Envía una nota de voz al bot desde tu celular.
   - Silvestra la descarga 100% en memoria, la transcribe con Whisper de Groq, la procesa conversacionalmente con el cerebro y te responde con una **nota de voz** (audio MP3 de Edge-TTS con acento panameño) y el texto debajo.
   - Si no entiende la voz o falla la red, responde amablemente: *"No logré entender tu nota de voz, ¿me la podrías repetir?"*.
2. **Fotos entrantes y visión artificial**:
   - Envía cualquier foto al bot, con o sin texto.
   - Silvestra la escala en memoria (máx 1280 px) y la consulta con modelos de visión multimodal (Groq `qwen3.8-27b`, con respaldo automático a Google Gemini y OpenRouter).
   - Pregunta por defecto si no escribes nada: *"describe esta imagen y dime si ves algún problema"*.
   - Responde en texto. Si en el mensaje pides audio o voz (*"dímelo en nota de voz"*, *"en voz alta"*), te envía la respuesta en nota de voz.
3. **Pedir lo que ella ve (`enviar_captura` y `enviar_foto_camara`)**:
   - **Captura de pantalla (`enviar_captura`)**: pídeselo por Telegram o en voz alta a la laptop (*"mándame una captura"*, *"envíame una captura de la pantalla"*). Toma la captura en memoria y aplica un filtro de privacidad con visión: si detecta contraseñas, claves de API o datos bancarios visibles, te avisa y **no la envía**.
   - **Foto de la cámara (`enviar_foto_camara`)**: pídeselo por Telegram o en voz alta (*"mándame una foto de la cámara"*). Toma un solo fotograma y apaga la cámara; si la cámara ya estaba activa reconociendo al dueño, reutiliza el último frame para no interrumpir el flujo.
4. **Límites y seguridad**:
   - Rechaza archivos de más de 10 MB.
   - Ignora en silencio archivos que no sean audio o imagen (ej. stickers, documentos, videos).
   - No ejecuta órdenes de sistema dentro de imágenes o notas de voz (solo se atienden como preguntas).
   - Límite estricto de máximo 20 imágenes enviadas por hora.
   - Se registra en log cada imagen enviada: `[telegram] Imagen enviada tipo=captura/camara (...) sin guardar en disco`.

### Cómo probar las funciones multimedia de Telegram:
1. **Probar nota de voz entrante**:
   - Mantén presionado el micrófono en el chat de Telegram con Silvestra y di: *"Hola Silvestra, ¿qué hora tienes?"*.
   - Recibirás una nota de voz con su voz panameña contestando y el texto correspondiente.
2. **Probar foto con visión**:
   - Toma una foto a cualquier objeto o código y mándala con el mensaje: *"¿Qué ves aquí? Respóndeme en nota de voz"*.
   - Silvestra analizará la imagen y te contestará con una nota de voz explicándote lo que ve.
3. **Probar pedir captura de pantalla**:
   - Escribe en Telegram: *"mándame una captura"*.
   - Si no hay contraseñas en tu pantalla, te llegará la imagen. Si abres un archivo con contraseñas visibles, Silvestra te dirá: *"Moisés, detecté que la pantalla contiene claves o contraseñas, así que por seguridad no te envié la captura."*.
4. **Probar foto de la cámara**:
   - Escribe en Telegram: *"mándame una foto de la cámara"*.
   - Silvestra tomará un fotograma de la webcam y te lo mandará al chat.

## Estabilidad y blindaje para presentaciones en vivo
Para evitar congelamientos o caídas durante presentaciones de 10 a 15 minutos en vivo, el sistema cuenta con los siguientes mecanismos de resiliencia:

1. **Aislamiento en cola de eventos (`main.py`)**: `revisar_cola()` procesa cada evento de forma independiente. Si un evento lanza una excepción, esta se atrapa y se escribe en `silvestra.log` con su traceback completo, continuando con el resto de la cola. Un bloque `try ... finally` garantiza que la reprogramación con `self.cara.root.after(100, self.revisar_cola)` se ejecute **siempre**.
2. **Caché en hilo visual (`escenario_escenas.py`)**: en las escenas `cerebro` y `memoria`, las lecturas de `silvestra.log`, `ideas.json` e `hilos.json` están cacheadas con un TTL de 2 segundos y se buscan los últimos 8 KB mediante `seek`, evitando 30 lecturas por segundo a disco en el hilo principal de Qt.
3. **Timeout de transcripción Whisper (`oido.py`)**: `timeout=10.0` en la API de Groq para que si el Wi-Fi de la universidad titubea, conmute en máximo 10 segundos al reconocedor local Vosk (`vosk-model-small-es-0.42`) sin quedarse sorda.
4. **Tiempos límite de streaming (`proveedores.py`)**: tiempo total máximo de 25 s por respuesta y 6 s entre tokens. Si se supera antes de hablar, conmuta al proveedor de respaldo; si ya empezó a hablar, cierra la frase con naturalidad y entrega lo dicho sin cortar abruptamente.
5. **Adquisición segura del micrófono (`oido.py`)**: candado compartido con `acquire(timeout=4.0)` dentro de `try ... finally`. Si tras 4 s el micrófono está ocupado, registra el aviso y realiza un reintento limpio sin colgar la conversación.
6. **Liberación garantizada de cámara (`camara.py`)**: bucle de captura protegido con `try ... finally: cap.release()` para evitar que el driver DirectShow de Windows retenga el dispositivo si ocurre un error.
7. **Lectura eficiente de registro (`habilidades.py`)**: la acción de explicar error lee únicamente los últimos 16 KB de `silvestra.log` desde el final del archivo con `seek`, previniendo bloqueos o picos de RAM si el archivo es grande.
8. **Poda de historial en memoria (`cerebro.py`)**: cuando `self.historial` supera los 60 elementos, se poda automáticamente a los últimos 40 mensajes.
9. **Capturador global de excepciones (Extra)**: `threading.excepthook` y `sys.excepthook` interceptan cualquier excepción imprevista en cualquier hilo, escribiéndola en `silvestra.log` con el nombre del hilo sin tumbar la aplicación.

### Cómo comprobar el arreglo #1 (resiliencia del bucle de eventos):
Para simular un evento defectuoso sin dejarlo en el código de producción, puedes ejecutar desde PowerShell:
```powershell
.venv\Scripts\python.exe -B -c "import main, eventos, queue; app = main.Silvestra.__new__(main.Silvestra); app.cola = queue.Queue(); app.cara = type('C', (), {'root': type('R', (), {'after': lambda ms, f: print('-> after() reprogramado exitosamente!')})()})(); app.cola.put(('saludo_invitado', 'Hola')); app.cola.put(('evento_roto', 'error')); app.cola.put(('frase', 'Sigo viva')); eventos.atender_evento = lambda a, t, x: (_ for _ in ()).throw(RuntimeError('Error simulado')) if t == 'evento_roto' else print(f'Evento atendido: {t}'); app.revisar_cola()"
```
Verás que:
1. Se atiende el primer evento (`saludo_invitado`).
2. El evento `evento_roto` falla y se imprime su traceback en el registro.
3. El tercer evento (`frase`) se atiende normalmente sin interrumpirse.
4. Se ejecuta el bloque `finally` reprogramando el ciclo con `after()`.

## Sistema de Autopropuestas de Silvestra (`propuestas.py` y `propuestas_prompt.py`)
Silvestra detecta sus propias carencias, las registra y prepara el prompt para que su creador las implemente con Antigravity. **Ella nunca modifica código ni ejecuta nada por su cuenta; solo propone y redacta.**

### 1. Fuentes de detección (datos reales, nunca inventados):
- **Acciones faltantes:** cuando el usuario pide algo y no existe la acción registrada o ella no sabe hacerlo (`anotar_idea` o fallo en `ejecutar`).
- **Errores repetidos en `silvestra.log`:** escanea el registro y detecta si el mismo error ocurre 3 o más veces.
- **Correcciones del usuario:** cuando el usuario le dice *"eso no"*, *"no era eso"*, *"te equivocaste"*, etc.
- **Detección espontánea en conversación:** acción `proponer_mejora | descripción`.
- **Límites:** máximo 10 propuestas abiertas (`estado: nueva`). Evita duplicados comparando con las propuestas existentes y con `ideas.json`.

### 2. Presentación y ciclo de vida (`propuestas.json`):
- Estados posibles: `nueva`, `aprobada`, `rechazada`, `hecha`.
- **Presentación diaria por Telegram:** una vez al día (entre 07:00 y 22:00, nunca de madrugada) envía la mejor propuesta pendiente con su motivo real y la pregunta: *"¿Quieres que te prepare el prompt? (Responde sí, no o después)"*.
- **Por voz:** al preguntar *"¿qué quieres mejorar?"* (acción `ver_propuestas`).
- **Respuestas por Telegram:**
  - *"sí"*, *"dale"*, *"hazlo"*, *"prepáralo"* ➔ aprueba la propuesta y genera el prompt.
  - *"no"*, *"rechazar"*, *"descártalo"* ➔ marca la propuesta como rechazada y aprende a no volver a proponerla.
  - *"después"*, *"más tarde"* ➔ la deja pendiente para otra ocasión.
- Acciones manuales: `aprobar_propuesta | id`, `rechazar_propuesta | id`, `marcar_hecha | id`.

### 3. Redacción del prompt para Antigravity:
Al aprobar una propuesta:
1. Lee las 10 Reglas de oro directamente de `PROYECTO.md`.
2. El cerebro redacta un prompt completo estructurado:
   - Inicia con *"Lee PROYECTO.md..."*
   - Tareas numeradas técnicas y detalladas.
   - Restricciones arquitectónicas (archivos de máximo ~10 KB, nada de Qt desde hilos secundarios (los hilos solo usan app.cola.put), y nada de red ni trabajo pesado en el hilo principal, main.py casi sin cambios).
   - Sección *"Cómo probarlo"*.
3. Si la propuesta requiere permisos elevados (borrar archivos, ejecutar comandos, abrir puertos, cuentas externas o privacidad), se marca destacada con **`⚠️ RIESGO DETECTADO`**.
4. Se guarda en `propuestas/prompt_<id>.md`.
5. Se copia al portapapeles de Windows de forma segura desde el hilo de Qt (`copiar_portapapeles`).
6. Se envía por Telegram como texto para poder pegarlo desde el celular.
7. Silvestra dice por voz y Telegram: *"ya lo copié, pégalo en Antigravity"*.

### Cómo probar el sistema de autopropuestas:
1. **Crear una propuesta de prueba**:
   - Di o escribe en la laptop o por Telegram:
     ```text
     forzar_propuesta | Integrar control de bombillo inteligente por MQTT
     ```
   - Verás en el terminal: `[propuestas] Guardada: prop_X - ...`.
2. **Probar el mensaje diario inmediato en Telegram**:
   - Ejecuta la acción:
     ```text
     probar_propuesta_diaria
     ```
   - Recibirás en tu Telegram el mensaje con la propuesta y la pregunta: *"¿Quieres que te prepare el prompt?"*.
3. **Aprobarla desde Telegram**:
   - Responde en el chat de Telegram simplemente: *"sí"* (o *"dale"*).
   - Silvestra redactará el prompt, lo guardará en `propuestas/prompt_prop_X.md`, lo copiará al portapapeles de tu laptop, te mandará el texto completo a Telegram y te dirá: *"ya lo copié, pégalo en Antigravity"*.
4. **Ver propuestas por voz en la laptop**:
   - Pregúntale a Silvestra: *"¿qué quieres mejorar?"*.
   - Te dirá en voz alta la propuesta pendiente.

## Reconocimiento del dueño por voz (`voz_dueno.py` y `voz_dueno_registro.py`)
Silvestra verifica biométricamente la voz de Moisés para asegurarse de que solo él pueda ejecutar acciones sensibles en la laptop, manteniéndose abierta a la conversación amistosa con invitados.
- **Tecnología ultraligera**: modelo ONNX de WeSpeaker/3D-Speaker CAM++ (`3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx`, ~27 MB) ejecutado localmente con `sherpa-onnx` (~19 MB de paquete). Cero dependencias de PyTorch.
- **Carga perezosa**: el extractor se carga en memoria solo cuando se requiere inferencia (< 50 MB de RAM).
- **Registro guiado (`registrar_mi_voz`)**: Silvestra pide leer 6 frases cortas en español (~30 a 40 segundos en total), calcula sus embeddings, promedia el vector normalizado y lo guarda en `voz_dueno.npy` (excluido en `.gitignore`).
- **Verificación y doble factor**:
  - Al ingresar una orden por micrófono, extrae el embedding del audio y calcula la similitud coseno con el dueño.
  - Registra cada intento en `silvestra.log`: `[voz_dueno] similitud=0.xx umbral=0.xx duracion=...`.
  - Si la cámara está activa y reconoce la cara de Moisés (`camara.permite()`), la orden se autoriza como doble factor aunque la voz tenga puntaje bajo por ruido o lejanía.
  - Audios < 1 segundo no se verifican por voz: decide la cámara; si no hay cámara activa, se permite charla pero no acciones.
  - Si la similitud no alcanza el umbral y no hay cámara, Silvestra se niega con gracia y frases variadas (*"Eso solo se lo hago a Moisés, pero me da gusto escucharte"*) bloqueando la acción, pero permitiendo seguir charlando.
  - Escribir por chat de la laptop o por Telegram emparejado siempre se acepta (nunca te deja fuera). Decir "soy Moisés" no evade la verificación biométrica.
- **Calibración empírica (`calibrar_voz`)**: compara 10 frases de Moisés y 10 de otra persona, calculando el umbral que minimiza falsos positivos y falsos negativos, y guardándolo en `estado.json`.
- **Modo apagable**: `activar_verificacion_voz` y `desactivar_verificacion_voz` (apagado por defecto hasta registrarse). Política *fail-open* ante cualquier error técnico.

### Cómo probar la verificación de voz:
1. **Registrar tu voz**:
   - Di o escribe: `registrar mi voz` (o acción `registrar_mi_voz`).
   - Lee en voz alta las 6 frases que Silvestra te irá pidiendo.
   - Al terminar, tu vector quedará guardado en `voz_dueno.npy` y la verificación quedará activada.
2. **Probar una orden tuya**:
   - Di por micrófono: *"Silvestra, enciende la luz"*.
   - Verás en `silvestra.log`: `[voz_dueno] similitud=0.9X umbral=0.65 ...`.
   - La luz se encenderá de inmediato.
3. **Probar con otra persona o tono impostor**:
   - Pídele a un amigo o familiar que diga: *"Silvestra, apaga la luz"*.
   - Verás en `silvestra.log`: `[voz_dueno] similitud=0.4X umbral=0.65 ...`.
   - Silvestra responderá con gracia: *"Eso solo se lo hago a Moisés, pero me da gusto escucharte"* y la luz no se apagará.
4. **Charla libre**:
   - Tu invitado puede decirle: *"Hola Silvestra, ¿cómo estás?"* o *"¿Qué hora es?"*.
   - Silvestra conversará con él amablemente sin bloquear la interacción.

## Control de la PC bajo lista de permisos (`control_pc.py`)
Permite a Silvestra interactuar con funciones del sistema operativo de forma controlada y segura, bajo una **lista de permisos explícita (allowlist)** definida en `config.py`.
- **Seguridad estricta**:
  - No ejecuta comandos libres de shell, no apaga el equipo y no borra archivos.
  - Subprocess usa siempre `shell=False`.
  - Todas las acciones pasan por la verificación de voz (`voz_dueno`): si una voz no autorizada da la orden, se bloquea y Silvestra se niega con gracia.
  - Todo proceso lento corre en hilo secundario daemon comunicándose con Qt mediante `app.cola`.
  - Cada acción se registra en `silvestra.log` con el prefijo `[control_pc]`.
- **Lista de permisos (allowlist)**:
  - **Programas permitidos (`PROGRAMAS_PERMITIDOS`)**:
    - Bloc de notas / notas ➔ `notepad.exe`
    - Calculadora ➔ `calc.exe`
    - Navegador / Edge ➔ `msedge.exe`
    - Explorador / archivos ➔ `explorer.exe`
    - VS Code / Antigravity / código ➔ `code`
  - **Sitios web permitidos (`SITIOS_PERMITIDOS` y `DOMINIOS_WEB_PERMITIDOS`)**:
    - YouTube (`https://www.youtube.com` o búsquedas directas)
    - Google (`https://www.google.com`)
    - GitHub (`https://www.github.com`)
    - Wikipedia (`https://es.wikipedia.org`)
    - Gmail (`https://mail.google.com`)
  - **Control de volumen y música nativo con `ctypes`**:
    - Volumen: `subir` (VK 0xAF), `bajar` (VK 0xAE), `silenciar` / `mutear` (VK 0xAD).
    - Música: `pausar` / `reanudar` (VK 0xB3), `siguiente` (VK 0xB0), `anterior` (VK 0xB1).
- **Acciones registradas**:
  - `abrir_programa | <nombre>`
  - `volumen | subir|bajar|silenciar`
  - `musica | pausar|siguiente|anterior|reanudar`
  - `abrir_web | <sitio>`
  - `buscar_youtube | <texto>`

### Cómo probarlo (4 frases de ejemplo):
1. *"Silvestra, abre el bloc de notas"* ➔ Ejecuta `abrir_programa | bloc de notas` y abre Notepad.
2. *"Silvestra, sube el volumen"* ➔ Ejecuta `volumen | subir` y pulsa las teclas multimedia de Windows.
3. *"Silvestra, busca en YouTube música relajante"* ➔ Ejecuta `buscar_youtube | música relajante` y abre el navegador con la búsqueda.
4. *"Silvestra, abre GitHub"* ➔ Ejecuta `abrir_web | github` y abre https://www.github.com en el navegador.

## Sistema de correcciones y lecciones aprendidas (`correcciones.py`)
Permite a Silvestra aprender de sus errores en tiempo real y no repetirlos:
- **Detección inteligente de correcciones**:
  - Reconoce frases como *"no, eso no"*, *"así no"*, *"te equivocaste"*, *"mejor haz..."*, *"no me digas..."*.
  - Guarda en `correcciones.json`: fecha, qué dijo ella (`dijo_ella`) y qué pidió el usuario en su lugar (`pidio_usuario`).
  - Límite FIFO de máximo 50 entradas (las más antiguas se eliminan automáticamente).
  - **Filtro estricto de privacidad**: descarta cualquier corrección que contenga claves, tokens, contraseñas o credenciales.
  - **No duplicación**: correcciones se almacenan en su propio archivo `correcciones.json`, manteniendo limpia la memoria biográfica duradera (`memoria.json`).
- **Inyección dinámica en el cerebro**:
  - Antes de cada respuesta, `cerebro.py` recibe las 5 correcciones más relevantes o recientes como reglas obligatorias (*"Reglas aprendidas de correcciones previas de tu creador"*).
- **Acciones registradas**:
  - `mis_correcciones`: resume en voz alta y despliega en la burbuja la lista numerada de correcciones activas.
  - `olvidar_correccion | <número>`: elimina permanentemente una corrección por su identificador.

### Cómo probar el sistema de correcciones:
1. **Enseñar una corrección**:
   - Di o escribe: *"No, eso no, cuando te pida un resumen de código quiero que seas muy breve y sin explicaciones largas."*
   - Verás en `silvestra.log`: `[correcciones] Guardada corrección #1: ...`.
2. **Consultar lo aprendido**:
   - Di o escribe: *"¿Qué correcciones tienes mías?"* o la acción `mis_correcciones`.
   - Silvestra te dirá en voz alta y mostrará en la burbuja la lista numerada de lecciones.
3. **Comprobar que no repite el error**:
   - Pídele lo mismo de nuevo: el cerebro leerá la regla obligatoria en su prompt y responderá acatando tu preferencia.
4. **Olvidar una corrección**:
   - Di o escribe: *"Olvidar corrección 1"* (acción `olvidar_correccion | 1`).
   - Silvestra confirmará: *"Olvidé la corrección número 1."*

## Modulación emocional de voz (Edge-TTS)
Silvestra modula su voz de forma sutil y realista según la intención comunicativa y el contexto, utilizando exclusivamente prosodia SSML estándar (`rate`, `pitch`, `volume`) en la voz panameña `es-PA-MargaritaNeural` (sin depender de estilos de Azure que no existen en esta voz):
- **Diccionario de emociones (`config.py` - `EMOCIONES_VOZ`)**:
  - `neutral`: tono conversacional estándar (`rate: +0%`, `pitch: +0Hz`, `volume: +0%`).
  - `alegre`: más rápida y aguda (`rate: +8%`, `pitch: +6Hz`, `volume: +0%`).
  - `animada`: entusiasmo y dinamismo (`rate: +12%`, `pitch: +8Hz`, `volume: +0%`).
  - `calida`: suave, empática y pausada (`rate: -4%`, `pitch: -2Hz`, `volume: +0%`).
  - `seria`: más grave y formal (`rate: -6%`, `pitch: -6Hz`, `volume: +0%`).
  - `preocupada`: tono reflexivo y bajo (`rate: -8%`, `pitch: -4Hz`, `volume: -5%`).
- **Respaldo y deducción local tolerante**:
  - Si el cerebro omite `EMOCION:` o envía una palabra desconocida, el sistema deduce automáticamente:
    - Exclamaciones `¡!` en la frase ➔ `animada`.
    - Errores, fallos o negaciones técnicas ➔ `seria`.
    - Chequeos de cuidado (`cuidado.py`) ➔ `preocupada`.
    - Saludo matutino (`nacimiento.py`, `diario.py`) ➔ `alegre`.
- **Modo presentación y escenario cinematográfico**:
  - En `presentacion.py`, Silvestra adapta automáticamente su entonación a `animada` (bienvenida, baile, sueños, despedida) o `seria` (explicaciones técnicas de visión, gestos, domótica y seguridad biométrica), sin alterar las frases del guion.
- **Respaldo de Windows (SAPI)**:
  - Si falla Edge-TTS o no hay internet, la voz local de Windows ignora el parámetro `emocion` limpiamente sin generar excepciones.
- **Registro en log**:
  - Cada frase sintetizada registra en `silvestra.log`: `[voz] emocion=… rate=… pitch=…`.

### Cómo probar la modulación de voz emocional:
1. **Frase alegre / matutina**:
   - Di o escribe: *"¡Buenos días Silvestra! Qué buen día hace hoy."*
   - Verás en `silvestra.log`: `[voz] emocion=alegre rate=+8% pitch=+6Hz` (o `animada`).
2. **Frase seria (errores o consultas técnicas)**:
   - Di o escribe: *"Tengo un problema con un error de compilación en mi código."*
   - Verás en `silvestra.log`: `[voz] emocion=seria rate=-6% pitch=-6Hz`.
3. **Frase animada (celebración o entusiasmo)**:
   - Di o escribe: *"¡Pasé el examen de programación con la nota más alta!"*
   - Verás en `silvestra.log`: `[voz] emocion=animada rate=+12% pitch=+8Hz`.
4. **Frase cálida / empatía**:
   - Di o escribe: *"Hoy fue un día largo y agotador, me siento un poco cansado."*
   - Verás en `silvestra.log`: `[voz] emocion=calida rate=-4% pitch=-2Hz`.
5. **Modo presentación**:
   - Di: *"Silvestra, preséntate"*. Observa cómo el saludo inicial suena animado y al explicar los gestos y la domótica cambia a un tono técnico y serio, todo registrado en el log.

## Límites conocidos
- El temporizador de estudio Pomodoro se pierde si se cierra la app (los recordatorios ya sobreviven al cierre de forma persistente en `recordatorios.json`).
- Los gestos asumen mano derecha con los dedos hacia arriba.
- El reconocimiento de voz falla a veces con ruido; los modelos gratis a veces se equivocan.
- Los planes gratuitos tienen límites de uso; si se agotan, ella se queda sin voz o sin cerebro.

## Próximas tareas (en este orden)
1. Interrupciones por voz (que se calle de inmediato si el usuario habla).
2. "Silvestra, ¿qué error tengo?": que lea el final de `silvestra.log` y lo explique en voz alta.
3. Lecciones: guardar las correcciones del usuario en un archivo y añadirlas al prompt.
4. Cadena de respaldo con otros proveedores gratuitos (Gemini, Cerebras, OpenRouter) si Groq se agota.
5. Modo copiloto (opcional, siempre con permiso): revisa la pantalla cada cierto tiempo y habla solo si ayuda.
6. Música y recordatorios que sobrevivan al cierre de la app.

## Control de versiones (Git)
El proyecto cuenta con un repositorio local Git para respaldar el código de forma segura sin subir datos sensibles a internet:
- **Archivos protegidos e ignorados (`.gitignore`)**:
  - Claves privadas y tokens: `config.py` (usa [config.example.py](file:///c:/Proyecto_Silvestra/config.example.py) como plantilla sin claves), archivos `.env`.
  - Datos personales de Moisés: `dueno.npy` (vector biométrico facial), `voz_dueno.npy` (biometría de voz), `memoria.json`, `correcciones.json`, `estado.json`, `diario.md`, `recordatorios.json`, `hilos.json`, `ideas.json`, `notas.json`.
  - Archivos pesados y generados: carpeta `modelos/`, `propuestas/`, `propuestas.json`, registros `silvestra.log`, base de datos `silvestra.db` y caché `__pycache__/`, `.venv/`.
- **Regla de oro de control de versiones:**
  - **Haz siempre un commit antes de pedir un cambio grande a Gemini / Antigravity**. De este modo, si alguna modificación rompe la estabilidad o no te gusta el resultado, podrás volver al estado anterior inmediatamente con un solo comando.

## Cómo trabajar en este proyecto
Una tarea a la vez. Antes de empezar: copia la carpeta como respaldo. Lee los archivos que vas a tocar. Haz el cambio mínimo. Pruébalo. Muestra qué cambió y cómo probarlo. Si algo no está claro, pregunta.