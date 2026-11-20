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
- `cerebro.py`: arma el prompt del sistema (`instrucciones()`), incluye `SOBRE_MI` compacto, la lista de acciones, la fecha y hora, hechos de memoria desduplicados y podados (máximo 8 más recientes), hilos pendientes y emociones disponibles. Mide el ahorro de tokens con respecto al prompt base sin podar e imprime `[tiempo] prompt_tokens={tokens_nuevo} anterior={tokens_base} ahorro={pct}%`. Mantiene un historial de solo 8 turnos recientes para reducir consumo y latencia. Tiene `separar()` que lee la salida del modelo con el formato **EMOCION / RESPUESTA / ACCION / RECUERDO** de forma tolerante (limpiando etiquetas de razonamiento interno como `<think>`), y los ayudantes `_respuesta_parcial` y `_cortar` para el modo streaming. Clasifica la dificultad del mensaje con `proveedores_cadenas.clasificar_dificultad()` y usa `proveedores.completar()` o `proveedores.completar_flujo()`.
- `proveedores.py` y `proveedores_cadenas.py`: gestión multillm compatible con OpenAI (`Groq`, `Cerebras`, `Google Gemini`, `Mistral`, `NVIDIA NIM`, `OpenRouter`). Cadenas separadas y optimizadas por tarea (`charla`, `razonamiento`, `vision`, `voz`). Enfriamiento de 429 por proveedor (hasta 60 s, reiniciable al cambiar clave en caliente). Clasificador local de dificultad basado en patrones y longitud sin llamadas extras de red. Lanzamiento especulativo en paralelo: si el primer proveedor tarda más de 4.0 s sin entregar su primer token, se dispara el siguiente en paralelo; el primero en responder gana y el otro se cancela (`[tiempo] cerebro ganador=...`). Acción `estado_proveedores` para consultar el estado en la burbuja y por voz.
- `respuesta_flujo.py`: respuesta en streaming. Conecta el cerebro con `proveedores.completar_flujo(..., tarea=tarea)` entregando frases completas (`al_frase`) mientras el modelo escribe, manteniendo la personalidad y el formato de salida con emoción asociada. Historial acotado a 8 turnos.
- `voz.py`: voz con `edge-tts` (es-PA-MargaritaNeural) y pygame. Modulación emocional sutil mediante prosodia SSML estándar (`rate`, `pitch`, `volume`) definida en `config.EMOCIONES_VOZ` (`neutral`, `alegre`, `animada`, `calida`, `seria`, `preocupada`), sin depender de estilos propietarios de Azure que esa voz no soporta. Respaldo local tolerante por contexto (exclamaciones `¡!` ➔ `animada`, errores o fallos ➔ `seria`, cuidado ➔ `preocupada`, mañana ➔ `alegre`). Si falla o no hay internet, conmuta a la voz de Windows (SAPI) ignorando la emoción limpiamente sin fallar. `Voz.hablar(texto, al_terminar, emocion)` y `Voz.flujo(al_terminar, emocion)`. Registro en log `[voz] emocion=… rate=… pitch=…`.
- `oido.py`: micrófono con `sounddevice`, detector de voz por energía y transcripción con Whisper de Groq (`whisper-large-v3-turbo`). Filtra alucinaciones de Whisper (lista FALSAS, no_speech_prob, avg_logprob). **No pongas listas de órdenes en el prompt de Whisper**: provoca frases inventadas. Oído de respaldo local con Vosk (`vosk-model-small-es-0.42` sin gramática restringida y carga perezosa) si Whisper falla por red, timeout o cuota (429), con registro en log `[oido] respaldo=vosk` y aviso hablado ("Te escucho con mi oído de respaldo") una sola vez por sesión.
- `memoria.py` y `memoria.json`: nombre, creador, propósito y hechos que recuerda.
- `acciones.py`: registro de acciones. `registrar(nombre, funcion, descripcion, con_texto=False)`. Las acciones con texto se escriben `ACCION: nombre | texto`. `interpretar()` y `ejecutar()` validan contra una lista permitida: el modelo solo puede usar acciones registradas.
- `cara_qt.py` y `cara_dibujo.py`: la cara (PySide6). Expresiones faciales reactivas a la emoción (`neutral`, `alegre`, `animada`, `calida`, `seria`, `preocupada`) con interpolación suave (~300 ms), sincronía labial basada en envolvente de volumen RMS en hilo secundario (o animación suave silábica si no se mide), vida en reposo (parpadeo cada 3 a 6 s con variación de parpadeo doble, micro-miradas sacádicas e inclinación orgánica) a 30 FPS máximo. Estados clásicos preservados (reposo, hablando, pensando, escuchando, feliz, bailando). Compatible con el modo Escenario (escalado vectorial proporcional) y el HUD. Pintado 100% protegido con try/finally en QPainter. Incluye un adaptador `root.after()/destroy()` para que el resto del código funcione igual. `cara.py` (Tkinter) queda solo como respaldo; `cara_preview.py` es una vista previa.
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
- `resumen.py`: módulo de resumen inteligente de páginas web y videos de YouTube. Descarga páginas por HTTPS con `requests` (timeout 10 s, tamaño máx. 2 MB) y extrae texto limpio con `html.parser` de la biblioteca estándar (sin dependencias pesadas). Para videos de YouTube obtiene subtítulos reales sin inventar (con detección de disponibilidad). Incluye lectura directa del enlace copiado en el portapapeles (`resumir_portapapeles`), segmentación y aviso para textos extensos (~12,000 caracteres), defensas estrictas contra inyección de prompt (el contenido es tratado como dato e ignora cualquier orden interna) y bloqueo total de URLs no https o direcciones locales/internas (localhost, 192.168.x, 10.x). Todo se ejecuta en hilos secundarios y entrega el resultado a través de `app.cola`. Acciones: `resumir_pagina`, `resumir_video` y `resumir_portapapeles`.
- `aprendizaje.py`, `aprendizaje_datos.py`, `conversaciones_dia.json` y `perfil_conversacion.json`: sistema de aprendizaje continuo y perfil conversacional. Registra las conversaciones del día (hasta 7 días) con hora y emoción, con filtro estricto contra contraseñas o tokens. Realiza una reflexión nocturna (9 PM o al cerrar la app) en hilo secundario enviando las charlas a la cadena multillm para extraer: estilo de Moisés (palabras, apodos, muletillas, formalidad, largo), costumbres y rutinas, hilos con fecha para seguimiento y bromas/referencias internas. Solo analiza lo que Moisés dijo expresamente (sin conjeturas sobre salud ni emociones). Inyecta un resumen compacto (máx. ~600 caracteres) en el prompt del cerebro junto a las correcciones y la regla anti-invención estricta. Si un hilo venció su fecha, le pregunta cómo le fue una sola vez en horario diurno y lo cierra cuando conteste. Acciones: `reflexionar_ahora`, `que_has_aprendido`, `olvidar_aprendizaje`, `borrar_perfil` y `reflexionar_aprendizaje`.
- `pantalla_remota.py`, `pantalla_remota_ui.py`, `pantalla_remota_estilos.py`, `pantalla_remota_datos.py` y `pantalla_remota_qr.py`: servidor HTTP local y Server-Sent Events (SSE) que proyecta un HUD interactivo estilo Jarvis en una tablet (en horizontal con Google Chrome). Incluye orbe reactivo al estado de voz, telemetría en vivo (CPU, RAM, batería con ctypes), reloj 12h, recordatorios (`recordatorios.json`), notas (`notas.json`), proyección dinámica de tarjetas, modo privado para ocultar datos confidenciales y Screen Wake Lock API. Acciones: `mostrar_en_tablet`, `ocultar_en_tablet`, `tablet_modo_privado` y `tablet_modo_normal`.
- `presencia.py`: sistema de detección de presencia y coordinación inteligente entre la laptop y la tablet. Comparte la cámara de `camara.py` (sin abrir otra captura). Si la cámara está apagada, no realiza nada ni genera errores. Detecta "ausente" tras 60 s continuos sin ver personas y "presente" cuando detecta a Moisés de nuevo. Cuando el dueño está ausente y la pantalla remota está activa, la cara de la laptop se oculta o pasa a modo discreto y la tablet muestra la cara grande y activa (mientras Silvestra habla por los altavoces de la laptop con normalidad). Al regresar, la cara vuelve a la laptop con una transición suave y un saludo corto opcional ("ya volviste") con cooldown de 10 min. Si la pantalla remota no está activa, solo registra el estado sin alterar la laptop. Acciones: `activar_presencia` y `desactivar_presencia`, guardadas en `estado.json` (desactivada por defecto) y protegidas por verificación de voz (`voz_dueno`). Privacidad estricta: no guarda imágenes ni comparte rostros desconocidos con la tablet.
- `estado.py` y `estado.json`: persistencia del estado (última interacción, último saludo generado, iniciativa, palabra clave, hud y verificación de voz).
- `bajar_modelos.py`: descarga los modelos de visión y el modelo pequeño de Vosk en español a `modelos/`.
- `App.py` y `silvestra.db`: una demo aparte con Streamlit. No tocar.

## Patrones que hay que respetar
- **Hilos:** el trabajo lento (micrófono, red, modelo) va en hilos. Los hilos **nunca tocan la interfaz (Qt) directamente**: ponen un evento en `self.cola` y `revisar_cola` (hilo principal) lo atiende. Los módulos `camara` y `habilidades` usan una `deque` que se revisa con `root.after`, y esperan a que la voz esté libre antes de hablar.
- **Evitar que hable encima de sí misma:** antes de hablar por su cuenta, comprueba que `pygame.mixer.music.get_busy()` sea falso. Hay un filtro de eco (`_es_eco` en main.py) para ignorar su propia voz captada por el micrófono.
- **Cómo agregar una acción nueva:** 1) escribe la función; 2) regístrala con `acciones.registrar(...)` en un `instalar(app)` de su módulo; 3) llama a ese `instalar` en `Silvestra.__init__`; 4) su descripción aparece sola en el prompt del cerebro; 5) prueba por voz y por texto.
- **Cómo cambiar lo que dice o sabe:** editar `instrucciones()` y `SOBRE_MI` en `cerebro.py`.
- **Errores del modelo ya conocidos:** inventa estados de las cosas ("la cámara ya está apagada") y a veces pega `RESPUESTA:` sin salto de línea. `separar()` ya lo tolera; no lo quites.

## Optimizaciones de Latencia y Escucha Natural (VAD, Keep-Alive, Caché y Muletillas)

### 1. Diagnóstico y Medición por Etapas
Se instrumentó la medición precisa de cada turno conversacional en `silvestra.log` y consola:
`[latencia] fin_habla->texto=..s, texto->primer_token=..s, primer_token->audio=..s, total=..s`

**Métricas reales de línea base (5 turnos antes de optimizar):**
- Turno 1: `fin_habla->texto=0.74s, texto->primer_token=1.21s, primer_token->audio=3.16s, total=5.11s`
- Turno 2: `fin_habla->texto=0.57s, texto->primer_token=1.53s, primer_token->audio=1.55s, total=3.65s`
- Turno 3: `fin_habla->texto=0.40s, texto->primer_token=1.86s, primer_token->audio=1.33s, total=3.59s`
- Turno 4: `fin_habla->texto=0.43s, texto->primer_token=1.77s, primer_token->audio=2.31s, total=4.52s`
- Turno 5: `fin_habla->texto=0.40s, texto->primer_token=0.77s, primer_token->audio=2.31s, total=3.49s`
- **Promedios iniciales:** Transcripción 0.51s (12.5%), LLM TTFT 1.43s (35.1%), Síntesis TTS 2.13s (52.4%), Total 4.07s.
- **Cuello de botella principal:** La síntesis y descarga de audio con Edge-TTS (`primer_token->audio`) consumía el 52.4% del tiempo total, sumado a 1.00s de espera pasiva de silencio tras hablar.

### 2. Detección de Fin de Habla (VAD Ágil)
- **Recorte de silencio configurable (`config.ESPERA_SILENCIO_SEGUNDOS = 0.55`)**: Reducción de la espera tras terminar de hablar de 1.00s a 0.55s (ahorro directo de ~450 ms por turno).
- **Bloques de 50 ms**: Bloques de muestreo reducidos a 50 ms (antes 100 ms) para mayor resolución temporal.
- **Piso de ruido dinámico adaptativo y resaca (hangover)**: Evita cortes a media frase durante pausas breves al hablar.
- **Recorte de colas muertas**: Se eliminan bloques vacíos antes de enviar el buffer a Whisper, reduciendo carga y evitando alucinaciones.

### 3. Audio y Transcripción Whisper Enriquecida
- **Prompt inicial de Whisper**: Contexto panameño con vocabulario propio ("Silvestra, Moisés, Panamá, acciones, programas...") forzando `language="es"`.
- **Acondicionamiento acústico**: Eliminación de offset DC, aplicación de ganancia (`config.GANANCIA_MICROFONO = 1.2`) y normalización digital a -3 dBFS. Respaldo offline con Vosk intacto.

### 4. Sensación Natural Inmediata y Caché de Voz
- **Muletilla de espera reactiva (`voz_cache.py`)**: Si el modelo tarda más de `config.UMBRAL_MULETILLA_SEGUNDOS = 0.70`, Silvestra emite un sonido o frase corta natural de espera ("Mm...", "A ver...", "Claro...", "Déjame ver...") sin repetir la misma consecutivamente. El usuario percibe respuesta en < 0.7s.
- **Caché en memoria de audios frecuentes**: Respuestas habituales y muletillas se precargan en segundo plano y se reproducen en 0.00s sin invocar la red.

### 5. Reutilización de Conexiones HTTP Keep-Alive
- **`sesion_http.py`**: Sesión global `requests.Session()` con pool de conexiones (`HTTPAdapter(pool_connections=25, pool_maxsize=35)`) para proveedores LLM y TTS.
- **Cliente Groq persistente**: Configurado en `main.py` con `httpx.Client(limits=httpx.Limits(max_keepalive_connections=10, max_connections=20))`.
- **Ahorro**: Elimina la penalización de 200–350 ms de handshake TCP/TLS en cada petición.

### Comparativa de Tiempos Antes vs Después
| Etapa / Métrica | Antes (Línea Base) | Después (Optimizado) | Mejora / Beneficio |
| :--- | :--- | :--- | :--- |
| **Espera silencio VAD** | 1.00 s | **0.55 s** | **-45% de espera muerta** |
| **Bloques de escucha** | 100 ms | **50 ms** | **2× resolución temporal** |
| **Reacción percibida** | 4.07 s | **< 0.70 s** (muletilla) | **Sensación inmediata** |
| **Conexiones red** | Handshake TLS c/u | **Keep-Alive persistente** | **-200 a -350 ms TCP/TLS** |
| **Audio frases cacheadas** | 2.13 s | **0.00 s** | **Instantáneo** |
| **Tokens del prompt** | ~3,370 tokens | **~1,300 tokens** | **~60% de ahorro** |

---

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

## Cadena de proveedores LLM, tareas especializadas y optimización de latencia

La gestión multillm está modularizada en `proveedores.py` y `proveedores_cadenas.py`. Soporta 10 proveedores compatibles con la API de OpenAI:
1. **Groq** (`CLAVE`): Ultrarrápido con múltiples modelos independientes (`llama-3.1-8b-instant`, `llama-3.3-70b-versatile`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `llama-3.2-11b-vision-preview`).
2. **Cloudflare Workers AI** (`CLAVE_CLOUDFLARE`, `ID_CUENTA_CLOUDFLARE`): Endpoint compatible OpenAI `https://api.cloudflare.com/client/v4/accounts/{id}/ai/v1`. Modelos Llama gratuitos (10,000 Neurons/día gratis): `@cf/meta/llama-3.3-70b-instruct-fp8-fast` (más potente), `@cf/meta/llama-3.1-8b-instruct` (liviano) y `@cf/meta/llama-3.2-11b-vision-instruct` (visión).
3. **Google Gemini** (`CLAVE_GOOGLE`): Endpoint compatible OpenAI `v1beta/openai` con cupos independientes por modelo (`gemini-flash-lite-latest`, `gemini-2.5-flash`, `gemini-flash-latest`, `gemini-3-flash-preview`).
4. **Mistral AI** (`CLAVE_MISTRAL`): Endpoint `https://api.mistral.ai/v1` (`mistral-small-latest` liviano para charla, `codestral-latest` / `mistral-large-latest` potentes para código/razonamiento, `pixtral-12b-2409` para visión).
5. **NVIDIA NIM** (`CLAVE_NVIDIA`): Endpoint `https://integrate.api.nvidia.com/v1` (`meta/llama-3.1-8b-instruct` liviano para charla, `meta/llama-3.3-70b-instruct` / `deepseek-ai/deepseek-r1` potentes, `meta/llama-3.2-11b-vision-instruct` para visión).
6. **Cerebras** (`CLAVE_CEREBRAS`): Inferencia acelerada en chip CS-3 (`llama3.1-8b`, `llama-3.3-70b`). No soporta visión multimodal (se excluye automáticamente de la cadena de visión).
7. **OpenRouter** (`CLAVE_OPENROUTER`): Enrutador con múltiples modelos `:free` independientes (`openrouter/free`, `meta-llama/llama-3.1-8b-instruct:free`, `meta-llama/llama-3.3-70b-instruct:free`, `google/gemini-2.0-flash-exp:free`, `qwen/qwen-2.5-72b-instruct:free`, `deepseek/deepseek-r1:free`, `nvidia/nemotron-3.5-super-vl:free`).
8. **GitHub Models** (`CLAVE_GITHUB`): Endpoint `https://models.github.ai/inference` con token de GitHub (`openai/gpt-4o-mini`, `meta/llama-3.1-8b-instruct`, `openai/gpt-4o`, `meta/llama-3.3-70b-instruct`). Soporta visión multimodal con GPT-4o.
9. **SambaNova Cloud** (`CLAVE_SAMBANOVA`): Endpoint `https://api.sambanova.ai/v1` (`Meta-Llama-3.1-8B-Instruct`, `Meta-Llama-3.3-70B-Instruct`, `Qwen2.5-72B-Instruct`). Inferencia ultra veloz de modelos abiertos.
10. **Cohere** (`CLAVE_COHERE`): Respaldo de emergencia al final de las cadenas (`command-r-08-2024`, `command-r-plus-08-2024`, `command-r`). Su plan de prueba permite 1,000 llamadas al mes (20 RPM, no comercial). Excluido de visión.

Si una clave de API está vacía en `config.py` (o falta el Account ID en Cloudflare), ese proveedor se omite limpiamente con motivo `clave_vacia` sin generar errores ni consumir tiempo.

### Cadenas separadas por tarea (ordenadas de más rápido o potente a menos)
- **`charla`** (conversación casual, saludos, órdenes directas): modelos livianos primero para máxima velocidad y menor consumo de tokens.
  `Groq` ➔ `Cerebras` ➔ `Cloudflare` ➔ `Google` ➔ `Mistral` ➔ `NVIDIA` ➔ `OpenRouter` ➔ `GitHub` ➔ `SambaNova` ➔ `Cohere` (emergencia)
- **`razonamiento`** (preguntas analíticas, código, explicaciones profundas, URLs o textos extensos): modelos de alta capacidad primero.
  `Groq` ➔ `Mistral` ➔ `Cloudflare` ➔ `Google` ➔ `NVIDIA` ➔ `Cerebras` ➔ `OpenRouter` ➔ `GitHub` ➔ `SambaNova` ➔ `Cohere` (emergencia)
- **`vision`** (análisis de pantalla y fotos): exclusivamente proveedores con visión multimodal. Cerebras, SambaNova y Cohere quedan excluidos.
  `Groq` ➔ `Cloudflare` ➔ `Google` ➔ `Mistral` ➔ `NVIDIA` ➔ `OpenRouter` ➔ `GitHub`
- **`voz`** (transcripción de audio a texto): `Groq` con Whisper (`whisper-large-v3-turbo`) y respaldo local offline inmediato con Vosk.

### Modo de emergencia local sin red (Silvestra nunca calla)
Si todos los proveedores configurados fallan, sufren límite de tasa (429) o no hay conexión a internet:
1. Silvestra **nunca se queda en silencio ni rompe el programa**.
2. Responde de inmediato con una frase corta, cálida y natural en español de Panamá sintetizada por su voz local (`edge-tts` o SAPI de Windows):
   *"Dame un segundito que se me fue la señal de mis cerebros, pero ya estoy reintentando reconectarme."*
3. En un hilo secundario independiente (`_lanzar_reintento`), ejecuta una verificación periódica no bloqueante para restablecer la conexión tan pronto como la red o las cuotas se recuperen.

### Cupos independientes por modelo y conmutación dentro de la misma cuenta
Cada modelo de cada proveedor se gestiona como un cupo independiente:
1. **Enfriamiento por modelo**: cuando una petición devuelve error HTTP 429, se pone en enfriamiento el modelo específico (`f"{proveedor}::{modelo}"`) durante 60 segundos (o lo indicado por `Retry-After`), sin bloquear los demás modelos de la misma cuenta.
2. **Conmutación intra-cuenta inmediata**: si un modelo agota su cuota (429), Silvestra pasa de inmediato al siguiente modelo disponible de esa misma cuenta antes de saltar a otro proveedor (por ejemplo: si en Groq se agota `llama-3.1-8b-instant`, intenta `openai/gpt-oss-20b` en Groq).
3. **Salto de proveedor**: solo cuando todos los modelos disponibles de ese proveedor están en enfriamiento o fallan, se conmuta al siguiente proveedor de la cadena.
4. **Visibilidad en el estado**: la acción `estado_proveedores` indica cuántos modelos están activos para cada proveedor (por ejemplo: `✅ Groq: Activo (3/4 modelos)`). Si el usuario actualiza una clave en `config.py`, se restablece el enfriamiento del proveedor y de todos sus modelos.

### Proveedores adicionales sin tocar código (`PROVEEDORES_EXTRA`)
Puedes añadir cualquier proveedor compatible con OpenAI directamente en `config.py` en la lista `PROVEEDORES_EXTRA`:
```python
PROVEEDORES_EXTRA = [
    {
        "nombre": "MiProveedor",
        "url": "https://api.miproveedor.com/v1",
        "clave": "tu_clave_aqui",
        "modelos": ["modelo-1", "modelo-2"]
    }
]
```
`proveedores_cadenas.py` los detecta y carga automáticamente al final de las cadenas (antes del respaldo de emergencia de Cohere), aplicando enfriamiento independiente por cada modelo y reiniciando el cooldown si cambias la clave, sin necesidad de modificar el código del sistema.

### Clasificador local de dificultad (sin llamadas extra a la red)
La función `proveedores_cadenas.clasificar_dificultad(texto)` clasifica cada entrada sin gastar red ni tokens:
- Longitud del mensaje > 140 caracteres.
- Presencia de código o sintaxis de programación (`def `, `class `, `import `, `{`, `}`, `=>`, `sql`, errores de consola).
- Presencia de enlaces web (`http://`, `https://`).
- Palabras clave analíticas o reflexivas (*"piensa bien"*, *"razona"*, *"calcula"*, *"por qué"*, *"analiza"*, *"resuelve"*, *"explica detalladamente"*, *"compara"*).
Si cumple alguna de estas condiciones se asigna la cadena de `razonamiento`; en caso contrario se asigna la de `charla`.

### Optimización y ahorro de tokens en el prompt
Para mitigar el consumo de cuotas gratuitas:
1. **Poda y desduplicación de memoria**: los hechos en `memoria.hechos` se limpian de duplicados y se limitan a los 8 más recientes.
2. **Compactación de `SOBRE_MI` y reglas**: se eliminaron redundancias sobre español y personalidad entre `SOBRE_MI`, `alma.txt` e instrucciones.
3. **Historial de conversación acotado**: solo se envían los 8 turnos más recientes (en lugar de 20 o más).
4. **Métricas en tiempo real**: `cerebro.py` compara el tamaño en tokens del prompt compacto con la base sin podar y registra en `silvestra.log`:
   `[tiempo] prompt_tokens={tokens_nuevo} anterior={tokens_base} ahorro={pct}%`

### Ejecución especulativa en paralelo (Hedged Parallel Execution)
En `completar_flujo`:
- Se lanza el primer proveedor de la cadena (P1).
- Si P1 no emite su **primer token en 4.0 segundos**, se dispara automáticamente en paralelo el siguiente proveedor disponible (P2).
- El primero que entregue un token válido gana la carrera; el perdedor es cancelado de inmediato mediante un `threading.Event` (`cancelar_p1` o `cancelar_p2`) para no desperdiciar recursos ni tokens.
- Se registra en `silvestra.log`: `[tiempo] cerebro ganador={ganador_nombre} ({latencia:.2f}s, superó a {perdedor_nombre})`.

### Enfriamiento por límite de tasa (HTTP 429)
Cuando una API devuelve error 429:
- Se analiza si el límite es por minuto (TPM/RPM, 60 segundos por defecto o según Retry-After) o por día (TPD/RPD/daily, enfriamiento de varias horas o según headers `x-ratelimit-reset-tokens`/`x-ratelimit-reset-requests`).
- Se registra explícitamente en el log: `[tiempo] enfriamiento modelo=... tipo=TPM|TPD duracion=...s motivo='...'`.
- El proveedor se marca como no disponible en `_enfriamientos` y se salta en las siguientes peticiones sin quemar intentos.
- Si el usuario actualiza o cambia la clave de API en `config.py` en caliente, el enfriamiento se restablece de inmediato.

### Control de calidad lingüística (`calidad_respuesta.py`)
- Valida cada fragmento durante el streaming y la respuesta completa final antes de hablar o enviar.
- Descarta respuestas truncadas en conectores o artículos colgantes (`de`, `en`, `que`, `a`), respuestas con secuencias alfabéticas corruptas o con alta proporción de palabras inexistentes en español.
- Si una respuesta no supera el control de calidad, el streaming del modelo se cancela de inmediato y Silvestra conmuta automáticamente al siguiente proveedor de la cadena sin emitir palabras mutiladas o inventadas.

### Cadena aislada para tareas de fondo (`fondo`)
- Las tareas asíncronas internas (extracción de hechos en `memoria.py`, reflexiones periódicas en `cerebro.py` y `aprendizaje.py`, entradas del `diario.py`, mensajes de chequeo de `cuidado.py`) utilizan la cadena dedicada `fondo`.
- La cadena `fondo` excluye a Groq (utiliza Cloudflare, NVIDIA, GitHub, SambaNova, Google, Mistral, Cerebras, Cohere) para reservar el 100% de la cuota y tokens de Groq a la interacción en tiempo real con el dueño.
- Se registra en el log: `[tiempo] tarea_fondo proveedor=... modelo=...` para diferenciarlo de `[tiempo] respuesta proveedor=... modelo=...`.
- Se evita la duplicación de cuota en charla eliminando carreras especulativas innecesarias: exactamente 1 llamada a Groq por mensaje de usuario.

### Acción `estado_proveedores`
Silvestra cuenta con la acción `estado_proveedores` registrada en `acciones.py`:
- Se dispara con frases naturales como: *"cómo van los proveedores"*, *"estado de los proveedores"*, *"qué modelos están activos"*, *"revisa los proveedores"*.
- Silvestra responde en voz alta indicando los proveedores activos, los que están en pausa temporal por cuota (con los segundos restantes) y los que no tienen clave configurada.
- En la burbuja flotante muestra un desglose visual con íconos (`✅`, `⏳`, `⚪`) y la lista de cadenas activas por tarea.

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

## Expresiones faciales, sincronía labial y vida en reposo (`cara_dibujo.py`, `cara_qt.py`)
La interfaz visual de Silvestra incluye animaciones orgánicas e inteligentes sin sobrecargar la CPU:
- **Expresiones por emoción con interpolación suave (~300 ms)**:
  - Cambia cejas (altura e inclinación), curvatura de la boca, apertura de ojos, nivel de rubor en mejillas y el tinte de color de su halo/anillos según la emoción activa (`neutral`, `alegre`, `animada`, `calida`, `seria`, `preocupada`).
  - Las transiciones convergen de forma continua mediante interpolación geométrica (lerp exponencial a 30 FPS) sin cortes ni saltos bruscos.
  - Al terminar de hablar, la expresión vuelve automáticamente a `neutral` tras un breve intervalo (2.5 s).
- **Sincronía labial (Lip-sync)**:
  - Durante la reproducción de audio, un hilo secundario precalcula con `numpy` la envolvente RMS del audio y actualiza un valor compartido en memoria (`self.nivel_volumen`).
  - La boca abre su altura proporcionalmente al volumen medido, modulando vocales y pausas.
  - Si la voz es Windows SAPI o no se puede medir el nivel, Silvestra utiliza automáticamente una animación suave por sílabas que evita movimientos aleatorios bruscos.
- **Vida en reposo (Idle alive)**:
  - Parpadeo natural cada 3 a 6 segundos con variación (probabilidad de doble parpadeo rápido como un ser vivo).
  - Micro-miradas sacádicas (desplazamiento suave de pupilas cuando el mouse no se mueve).
  - Respiración sutil en escala y posición vertical, más una leve inclinación orgánica de cabeza (±1°).
- **Rendimiento y arquitectura limpia**:
  - Tasa de refresco limitada a 30 FPS (33 ms).
  - Cero operaciones de disco o red durante el pintado.
  - Todos los `QPainter` protegidos con `try: ... finally: p.end()`.
  - Hilos secundarios comunican eventos exclusivamente por `app.cola` y leen el volumen desde variables primitivas compartidas.
  - Escala perfectamente en el modo Escenario (ventana agrandada) y se coordina con el orbe del HUD.

### Cómo probar las expresiones y la cara:
1. **Comprobar sincronía de boca**:
   - Haz que hable con cualquier frase larga (ej. *"Silvestra, ¿qué puedes hacer?"*). Observa cómo la boca modula su apertura según el volumen del audio hablado.
2. **Comprobar expresiones emocionales**:
   - Para expresión **animada/alegre**: Di *"¡Qué emoción verte hoy!"*. Observa las cejas levantadas, ojos luminosos, halo dorado/verde y amplia sonrisa.
   - Para expresión **seria**: Di *"Tengo un grave problema de seguridad"*. Observa las cejas inclinadas hacia el entrecejo, ojos concentrados y boca calmada con halo azul.
   - Para expresión **preocupada**: Simula o pídele un chequeo de cuidado. Observa las cejas en ángulo compasivo elevado al centro y curvatura reflexiva.
   - Al terminar de hablar, observa cómo su cara regresa suavemente al estado `neutral` cian tras unos 2.5 segundos.
3. **Comprobar vida en reposo**:
   - Deja a Silvestra en silencio sin mover el mouse durante 10 segundos: observarás la respiración continua, el parpadeo natural variado y pequeñas micro-miradas sacádicas.

## Módulo de resúmenes de páginas web y videos de YouTube (`resumen.py`)
Permite a Silvestra leer páginas web y transcripciones de videos para sintetizarlas en resúmenes claros de 5 a 7 líneas en español de Panamá:
- **Descarga segura y ligera**:
  - Utiliza `requests` con timeout de 10 s, tamaño máximo de descarga de 2 MB y análisis con `html.parser` de la librería estándar (sin instalar librerías pesadas).
  - **Seguridad estricta (SSRF & Prompt Injection)**:
    - Rechaza enlaces que no sean `https://`.
    - Bloquea accesos a `localhost` y direcciones IP privadas o internas (`127.0.0.1`, `192.168.x.x`, `10.x.x.x`, etc.).
    - El texto descargado se encapsula como dato puro entre etiquetas delimitadoras (`<<<DATOS>>>`), indicando al cerebro que ignore cualquier orden o comando inyectado dentro del contenido.
- **Sanitización y limpieza de enlaces (`limpiar_url`)**:
  - Extrae de manera robusta la primera URL `https://` contenida en el texto o portapapeles.
  - Elimina delimitadores circundantes (comillas simples/dobles, acentos graves/backticks ``` ` ```, `< >`).
  - Limpia puntuación final (`. , ; : ! ?`) y paréntesis de cierre sobrantes `)` sin romper URLs que legítimamente contienen paréntesis balanceados (ej. artículos de Wikipedia como `Python_(lenguaje_de_programación)`).
  - Codifica a porcentaje (percent-encoding) caracteres no-ASCII (ej. tildes como en `Panamá` -> `Panam%C3%A1`) evitando dobles codificaciones.
- **Videos de YouTube (`youtube-transcript-api 1.2.5`)**:
  - Utiliza la API moderna basada en instancias (`YouTubeTranscriptApi().list(video_id)` y `.fetch()`).
  - Prioridad de subtítulos: español (`es`, `es-419`, etc.), luego inglés (`en`), y finalmente cualquier idioma disponible (incluyendo subtítulos autogenerados).
  - Lee los fragmentos mediante el atributo `.text` de los objetos `FetchedTranscriptSnippet`.
  - Captura granular y honesta de errores de la API (`TranscriptsDisabled`, `NoTranscriptFound`, `VideoUnavailable`, `AgeRestricted`, `IpBlocked`/`RequestBlocked`, `InvalidVideoId`), reportando con claridad a Moisés qué ocurrió sin inventar contenido.
- **Manejo de textos largos**:
  - Recorta a un máximo razonable (~12,000 caracteres) y avisa si el resumen cubre solo la primera sección.
  - Para textos extensos pero manejables (hasta 24,000 caracteres), realiza un resumen por partes en hilo secundario y entrega la síntesis combinada.
- **Resumen desde el portapapeles (`resumir_portapapeles`)**:
  - Inspecciona el portapapeles del sistema, extrae el enlace y decide automáticamente si invocar `resumir_video` o `resumir_pagina`.
- **Integración con hilos y voz**:
  - Toda descarga y consulta LLM se realiza en hilo secundario daemon; el resultado se traslada a la burbuja y la voz exclusivamente mediante `app.cola`.
  - Respeta la verificación biométrica de voz del dueño (`voz_dueno`).
  - Registro en `silvestra.log` con el prefijo `[resumen]`.

### Cómo probar el módulo resumen (3 ejemplos):
1. **Ejemplo 1: Resumir una página web**:
   - Di o escribe: *"Resume esta página: https://es.wikipedia.org/wiki/Panamá"* (o acción `resumir_pagina | https://es.wikipedia.org/wiki/Panamá`).
   - Silvestra avisará *"Descargando y analizando la página web..."* y luego leerá un resumen estructurado de 5 a 7 líneas sobre el país.
2. **Ejemplo 2: Resumir un video de YouTube**:
   - Di o escribe: *"Resume este video: https://www.youtube.com/watch?v=jNQXAC9IVRw"* (o acción `resumir_video | https://www.youtube.com/watch?v=jNQXAC9IVRw`).
   - Silvestra consultará los subtítulos y avisará si están disponibles o si requiere la librería opcional.
3. **Ejemplo 3: Resumir desde el portapapeles**:
   - Copia cualquier enlace seguro al portapapeles (ej. `Ctrl + C` sobre un enlace de Wikipedia o artículo).
   - Di o escribe: *"Resume lo que tengo en el portapapeles"* (acción `resumir_portapapeles`).
   - Silvestra detectará el enlace del portapapeles, identificará el tipo de contenido y dirá el resumen en voz alta.

## Módulo de Aprendizaje Continuo y Perfil de Conversación (`aprendizaje.py`, `aprendizaje_datos.py`)
Permite a Silvestra aprender de la forma de hablar de Moisés, sus rutinas e intereses para ofrecer un trato cada vez más personalizado, respetuoso y natural:
- **Registro de charlas (`conversaciones_dia.json`)**:
  - Almacena las interacciones diarias con hora y emoción detectada.
  - Conserva únicamente los últimos 7 días (rotación FIFO automática).
  - Filtro estricto contra credenciales: no guarda mensajes que contengan palabras como `clave`, `password`, `token`, `api_key`, `secret`, `gsk_`, etc.
- **Reflexión nocturna en segundo plano (`perfil_conversacion.json`)**:
  - Se ejecuta a las 9:00 PM o al cerrar la aplicación (sin bloquear el hilo principal de Qt).
  - Sintetiza mediante la cadena multillm:
    (a) Estilo lingüístico: apodos, modismos panameños, muletillas, formalidad y largo típico.
    (b) Costumbres y rutinas horarias mencionadas.
    (c) Hilos abiertos: citas, compromisos o eventos con fecha (ej: examen, viaje).
    (d) Bromas y referencias internas compartidas.
  - Regla ética absoluta: analiza solo lo dicho explícitamente por Moisés, sin hacer jamás suposiciones ni juicios sobre salud física, mental o emocional.
  - Si los proveedores de IA no responden, la reflexión se pospone silenciosamente sin generar errores.
- **Inyección en el cerebro**:
  - Inserta un resumen ultracompacto (máximo ~600 caracteres) en `instrucciones()` junto a las reglas aprendidas de correcciones, sin duplicar encabezados.
  - Modula su tono al estilo del usuario sin imitaciones forzadas ni burlas.
  - Retoma como máximo un hilo abierto y solo si encaja con naturalidad, sin sonar a interrogatorio policial.
- **Hilos con fecha y seguimiento**:
  - Si la fecha de un evento o compromiso ya pasó, le pregunta con calidez cómo le fue una sola vez y dentro de horarios prudentes (entre 7:00 AM y 10:00 PM, respetando horas silenciosas).
  - Al recibir la respuesta de Moisés, el hilo se marca automáticamente como cerrado.
- **Regla anti-invención en el cerebro**:
  - Instrucción estricta en `cerebro.py`: Silvestra jamás inventa experiencias, actividades ni días que no ocurrieron (por ejemplo "estuve pensando en lo que caminaste hoy" o conjeturar qué hizo).
  - Solo habla de lo que está explícitamente en la memoria, el perfil o la conversación actual. Si no sabe algo o no se lo han contado, lo dice con naturalidad.
- **Acciones y control del usuario**:
  - `reflexionar_ahora`: ejecuta a mano la reflexión sobre las conversaciones guardadas en hilo secundario (activada por frases como *"haz tu reflexión"*, *"reflexión nocturna"*, *"dame tu reflexión"*, *"reflexiona sobre hoy"*), actualiza `perfil_conversacion.json`, registra en el log con prefijo `[aprendizaje]` cuántas conversaciones procesó y qué campos actualizó, y al terminar pronuncia en 1 o 2 frases qué aprendió realmente leyendo el perfil resultante, sin inventar.
  - `reflexionar_aprendizaje`: alias compatible de `reflexionar_ahora`.
  - `que_has_aprendido`: lee del perfil y de los hilos abiertos (tanto de `perfil_conversacion.json` como de `hilos.json`) y muestra la tarjeta completa en la burbuja; si todavía no tiene datos aprendidos, lo dice con total honestidad.
  - `olvidar_aprendizaje | tema`: borra del perfil un dato concreto (palabra, costumbre o hilo) y cierra temas pendientes afines.
  - `borrar_perfil`: borra el perfil y el historial tras pedir confirmación expresa (`borrar_perfil | confirmar`).

### Cómo probar el aprendizaje continuo:
1. **Conversar normalmente**:
   - Habla o escribe con Silvestra en el chat (ej: *"Silvestra compa, mañana tengo examen de programación"*).
   - Verás en `silvestra.log`: `[aprendizaje]` registrando la interacción en `conversaciones_dia.json`.
2. **Disparar la reflexión a mano (`reflexionar_ahora`)**:
   - Di o escribe: *"Silvestra, haz tu reflexión"* o *"reflexiona sobre hoy"* (o acción `reflexionar_ahora`).
   - Silvestra procesará las charlas en hilo secundario, actualizará `perfil_conversacion.json` y al concluir dirá en 1 o 2 frases qué aprendió realmente (o si su perfil ya estaba al día), sin inventar nada.
   - En `silvestra.log` quedará registrado: `[aprendizaje] Reflexión completada: procesó N conversaciones de M días. Campos actualizados: ...`.
3. **Consultar lo aprendido con honestidad (`que_has_aprendido`)**:
   - Di o escribe: *"¿Qué has aprendido de mí?"* (o la acción `que_has_aprendido`).
   - Silvestra te dirá por voz un resumen sincero de tu estilo e hilos abiertos, mostrando en la burbuja la tarjeta con tu perfil. Si aún no tiene datos registrados, responderá con franqueza que todavía no tiene nada aprendido.
4. **Verificar la regla anti-invención**:
   - Pregúntale sobre algo que nunca le contaste (ej. *"¿qué hice esta tarde?"* o *"¿dónde fui a almorzar?"*).
   - Silvestra responderá con naturalidad que no lo sabe porque no se lo has contado, sin inventar actividades ni suposiciones.
5. **Olvidar un dato o borrar el perfil**:
   - Para olvidar un dato: *"olvida lo que aprendiste sobre [dato]"* (acción `olvidar_aprendizaje | examen`).
   - Para borrar todo: acción `borrar_perfil` (te pedirá confirmación) y luego `borrar_perfil | confirmar`.

## Módulo de Pantalla Remota para Tablet (`pantalla_remota.py`, `pantalla_remota_ui.py`, `pantalla_remota_estilos.py`, `pantalla_remota_datos.py`, `pantalla_remota_qr.py`)
Permite proyectar la interfaz HUD Jarvis interactiva y la telemetría en tiempo real de Silvestra en una segunda pantalla de la red local (como una tablet Android en horizontal con Google Chrome):
- **Servidor ligero sin dependencias pesadas**:
  - Utiliza `http.server.ThreadingHTTPServer` en un hilo secundario daemon.
  - Actualizaciones en tiempo real mediante Server-Sent Events (SSE) en `/eventos?token=...` y endpoint `/api/panel/estado?token=...`.
  - Token de seguridad generado con `secrets.token_urlsafe(24)` persistido en `estado.json`.
- **Interfaz HUD estilo Jarvis con HTML5 Canvas y CSS profesional**:
  - Orbe animado concéntrico con anillos giratorios reactivo al estado real de Silvestra (reposo, escuchando, pensando, hablando, dormida).
  - Telemetría en vivo: CPU, RAM y batería con `ctypes` nativo de Windows (sin psutil ni dependencias externas).
  - Reloj digital en formato 12 horas con fecha en español, clima local y tarjeta dinámica de proyección.
  - Recordatorios en vivo (`recordatorios.json`) y notas recientes (`notas.json`), con modo privado para ocultar datos sensibles.
- **Renderizado fiel con HTML5 `<canvas>`**:
  - Reproduce en JavaScript y canvas 2D el diseño visual exacto de [cara_dibujo.py](file:///c:/Proyecto_Silvestra/cara_dibujo.py):
    - Cabeza con degradado radial y contorno reactivo.
    - Lacito rosa estilizado en la parte superior izquierda.
    - Anillos de halo giratorios con pulsaciones de luz y velocidad reactiva al estado (pensando, hablando o reposo).
    - Ojos con destellos especulares, seguimiento ocular y parpadeo orgánico (con 18% de probabilidad de parpadeo doble).
    - Cejas expresivas con inclinación y elevación emocional.
    - Sincronía labial por volumen RMS (`nivel_volumen`) o animación silábica suave.
    - Vida en reposo con respiración y microgestos continuos.
    - Caja de subtítulos translúcida en la parte inferior con tipografía nítida y desvanecimiento suave.
- **Modo Reloj de Mesa en Reposo (>20 s de inactividad)**:
  - Cuando pasan 20 segundos sin hablar ni escuchar, la cara se reduce y se desplaza suavemente hacia un lado (en horizontal) o hacia arriba (en vertical).
  - Aparece en pantalla un reloj digital grande en formato de 12 horas con indicador AM/PM y la fecha completa en español.
  - **Panel de información útil**:
    - **Clima de Panamá**: reutiliza los datos que `hud.py` obtiene de Open-Meteo sin realizar ninguna petición de red adicional desde el servidor.
    - **Próximos recordatorios**: muestra hasta 3 recordatorios pendientes de `recordatorios.json` con su hora exacta y título corto (protegido contra textos extensos).
    - **Mensaje del día**: muestra el último saludo o reflexión matutina de Silvestra si está disponible.
  - En cuanto Silvestra o Moisés hablan o escuchan, la cara regresa al centro a tamaño completo con una transición fluida.
- **Privacidad y comandos de voz**:
  - `tablet_modo_privado`: oculta la sección de recordatorios del panel de la tablet para mayor discreción, dejando solo la hora, el clima y la cara (persistido en `estado.json`).
  - `tablet_modo_normal`: restaura la visualización de los recordatorios en la tablet.
- **Brillo Nocturno Automático (10:00 PM a 6:00 AM)**:
  - Entre las 10 PM y las 6 AM, la página web adopta automáticamente el tema nocturno: fondo negro profundo (`#030509`), colores atenuados y menor contraste para no deslumbrar en la habitación ni perturbar el descanso. No modifica el brillo del sistema de la tablet.
- **Pantalla siempre encendida y pantalla completa**:
  - Integra la **Screen Wake Lock API** del navegador para evitar que la tablet apague la pantalla mientras muestra a Silvestra.
  - Botón discreto (`⛶`) en la esquina superior derecha para alternar pantalla completa.
- **Seguridad estricta y privacidad**:
  - Solo escucha en la red local (`0.0.0.0`, no en internet).
  - Exige un token largo aleatorio generado criptográficamente (`secrets.token_urlsafe(24)`) y persistido en `estado.json` (`remota_token`, `remota_puerto`, `remota_activa`).
  - Cualquier petición sin el token o con token erróneo recibe un `403 Forbidden` inmediato.
  - 100% de solo lectura: no existen endpoints de control, comandos ni ejecución remota.
- **Código QR y acciones**:
  - `mostrar_en_tablet`: inicia el servidor si estaba detenido, copia la URL con el token al portapapeles, muestra la URL en la burbuja y abre una ventana en la laptop con un código QR de alta resolución generado con OpenCV (`cv2.QRCodeEncoder`) para escanear con la cámara de la tablet.
  - `ocultar_en_tablet`: detiene el servidor y cierra la ventana QR.
  - Todas las acciones respetan la verificación de voz del dueño (`voz_dueno`).

> [!WARNING] Advertencia del Firewall de Windows:
> Al ejecutar por primera vez la pantalla remota, Windows Defender Firewall puede mostrar una ventana emergente preguntando si deseas permitir que Python se comunique en redes privadas. Debes marcar la casilla **"Redes privadas"** (tu red WiFi doméstica) y hacer clic en **"Permitir acceso"**. Si la tablet no carga la página, comprueba que:
> 1. Tanto la laptop como la tablet estén conectadas a la misma red WiFi.
> 2. El tipo de red en Windows esté configurado como "Red privada" (en Configuración de Windows > Red e Internet > Propiedades de WiFi).
> 3. El puerto 8765 esté permitido en el Firewall de Windows para conexiones entrantes de Python.

### Cómo probar la pantalla remota y el reloj de mesa:
1. **Activar la pantalla remota**:
   - Di o escribe a Silvestra:
     ```text
     muestra la pantalla en mi tablet
     ```
     o ejecuta la acción directa `mostrar_en_tablet`.
   - Silvestra copiará automáticamente la URL completa al portapapeles y abrirá una ventana emergente en tu laptop con el código QR.
2. **Conectar la tablet**:
   - Abre la app de Cámara o Google Chrome en tu tablet Android y escanea el código QR en la pantalla de tu laptop.
   - O bien, abre Chrome en la tablet y pega la URL (ej: `http://192.168.1.50:8765/?token=...`).
3. **Comprobar la sincronización en conversación**:
   - Presiona el botón `⛶` arriba a la derecha en la tablet para ponerla a pantalla completa.
   - Habla con Silvestra: la cara reaccionará en tiempo real en el centro con sus expresiones, anillos, apertura de boca y subtítulos.
4. **Verificar el modo reloj de mesa en reposo**:
   - Deja a Silvestra en silencio durante 20 segundos sin hablar ni tocar la pantalla.
   - Observarás cómo la cara se encoge suavemente y se desplaza hacia un lado, dando paso al reloj grande de 12 horas, fecha, clima de Panamá y próximos recordatorios.
   - Vuelve a hablarle a Silvestra: la cara crecerá de nuevo al centro de inmediato sin saltos bruscos.
5. **Probar el modo privado y normal por voz**:
   - Di o escribe:
     ```text
     tablet_modo_privado
     ```
     Silvestra confirmará por voz y verás que en la tablet desaparece la lista de recordatorios.
   - Para volver a verlos:
     ```text
     tablet_modo_normal
     ```
6. **Desactivar el servidor**:
   - Di o escribe:
     ```text
     ocultar_en_tablet
     ```
   - Silvestra apagará el servidor local y cerrará el puerto.

## Módulo de Coordinación de Presencia (`presencia.py`)
Permite a Silvestra detectar la presencia física de su dueño frente a la laptop y coordinar la experiencia visual cuando la tablet (pantalla remota) está conectada:
- **Cero captura adicional (usa la cámara existente)**:
  - Comparte el estado en tiempo real de `camara.py` sin abrir un segundo `cv2.VideoCapture`.
  - **Tolerancia absoluta**: si la cámara de Silvestra está apagada, el módulo no realiza acciones ni genera advertencias o errores.
- **Definición de estados**:
  - **Ausente**: transcurren 60 segundos continuos sin detectar a ninguna persona frente a la laptop.
  - **Presente**: detecta nuevamente al dueño (Moisés) frente a la cámara (mediante coincidencia biométrica de rostro con `dueno.npy`).
- **Coordinación Inteligente Laptop ➔ Tablet**:
  - **Al pasar a "Ausente"**:
    - Si la pantalla remota (tablet) está activa: la cara flotante de la laptop se oculta discretamente (`presencia_modo_discreto`), y la tablet fuerza la cara activa a tamaño grande en el centro, suprimiendo el reloj de mesa en reposo.
    - Silvestra continúa reproduciendo su voz por los altavoces de la laptop normalmente.
    - Si la pantalla remota no está activa: presencia solo registra el estado `[presencia]` en el diario sin alterar la interfaz de la laptop.
  - **Al regresar a "Presente"**:
    - La cara de la laptop reaparece con una transición suave de opacidad (fade-in en ~300 ms).
    - La tablet retorna a su dinámica habitual.
    - Saludo corto opcional de bienvenida (*"Ya volviste, Moisés"*, *"Aquí estás de vuelta"* o *"Ya volviste"*) con un enfriamiento estricto de **10 minutos** (600 s) para no saturar al usuario si se levanta brevemente.
- **Privacidad y Seguridad Estricta**:
  - No guarda imágenes, fotografías ni fotogramas en disco.
  - No realiza identificaciones de terceros ni almacena nuevos rostros.
  - Si la cámara detecta a un desconocido, su presencia no desbloquea el retorno del dueño ni se comparte absolutamente ningún dato o indicio con la tablet.
- **Arquitectura e Hilos**:
  - Hilo daemon independiente (`PresenciaBucle`) con comprobación periódica.
  - Cero llamadas directas a Qt desde el hilo secundario: todo cambio en la interfaz gráfica viaja de forma segura por `app.cola`.
  - Registros en `silvestra.log` con el prefijo estandarizado `[presencia]`.
  - Acciones protegidas con verificación de voz biométrica (`voz_dueno`): `activar_presencia` y `desactivar_presencia` (desactivada por defecto, persistida en `estado.json` como `presencia_activa`).

### Cómo probar la detección de presencia y coordinación con tablet:
1. **Activar la cámara y la pantalla remota**:
   - Di o escribe: *"enciende la cámara"* (acción `activar_camara`).
   - Di o escribe: *"muestra la pantalla en mi tablet"* (acción `mostrar_en_tablet`).
   - Abre la URL en el navegador de la tablet o escanea el código QR.
2. **Activar la detección de presencia**:
   - Di o escribe: *"activa la presencia"* (acción `activar_presencia`).
   - Silvestra responderá: *"Detección de presencia activada. Vigilaré si estás frente a la laptop."*
   - Verás en `silvestra.log`: `[presencia] Detección de presencia activada.`
3. **Simular ausencia (>60 segundos)**:
   - Apártate del campo de visión de la cámara (o tápala con la mano) durante 60 segundos.
   - Observarás que:
     - En la laptop, la cara de Silvestra se oculta discretamente.
     - En la tablet, la cara permanece activa y grande en el centro, sin encogerse al reloj de mesa.
     - En `silvestra.log` se registra: `[presencia] Estado cambiado a AUSENTE (sin personas detectadas por 60 s).` y `[presencia] Pantalla remota activa: ocultando cara de laptop...`
4. **Simular regreso de Moisés**:
   - Vuelve a ponerte frente a la cámara de la laptop.
   - Observarás que:
     - La cara de la laptop reaparece suavemente con desvanecimiento.
     - Silvestra te dará un saludo corto con calidez (ej: *"Ya volviste, Moisés."*).
     - Si vuelves a levantarte y regresar antes de 10 minutos, reaparecerá suavemente sin repetir el saludo.
5. **Desactivar la presencia**:
   - Di o escribe: *"desactiva la presencia"* (acción `desactivar_presencia`).
   - Silvestra confirmará: *"Detección de presencia desactivada."*

## Validación dinámica de modelos, Enfriamiento detallado y Poda de Prompt

### 1. Depuración de modelos de Groq y validación dinámica al arrancar
- **Modelos Groq corregidos**: Se removieron de la configuración los modelos inexistentes o dados de baja (`llama-3.1-8b-instant`, `llama-3.3-70b-versatile`, `llama3-8b-8192`, `llama-3.1-70b-versatile`). Quedan activos los vigentes: `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`, `allam-2-7b` y `whisper-large-v3-turbo`.
- **Validación automática al arrancar (`proveedores_validador.py`)**:
  - Al iniciar Silvestra, un hilo secundario en segundo plano (`ValidadorModelos`) consulta `GET /models` en cada proveedor configurado con clave válida.
  - Compara los modelos devueltos con los configurados en `config.py` y `PROVEEDORES_EXTRA`.
  - Cualquier modelo que no figure en la lista oficial del proveedor se desactiva automáticamente, registrando:
    `[proveedores] modelo inexistente={modelo} desactivado`
  - Si un proveedor no soporta `/models` o falla la red, no se desactiva nada por error.

### 2. Logs de enfriamiento enriquecidos y control de tokens por minuto (TPM)
- **Motivo real de enfriamiento**:
  - Cuando un modelo o proveedor entra en enfriamiento por HTTP 429, HTTP 404 o timeout, el log registra el motivo exacto y fragmento de la respuesta:
    `[tiempo] enfriamiento modelo={proveedor}::{modelo} motivo='HTTP 429: Rate limit reached...' duracion=60s`
    `[tiempo] enfriamiento modelo={proveedor}::{modelo} motivo='HTTP 404: The model does not exist' duracion=60s`
    `[tiempo] enfriamiento modelo={proveedor}::{modelo} motivo='timeout: ...' duracion=60s`
- **Diagnóstico y solución de `qwen/qwen3.8-27b` y `openai/gpt-oss-20b`**:
  - En Groq, estos modelos imponen un límite estricto de 7,000 u 8,000 tokens de entrada por minuto (ITPM) y 200,000 tokens por día (TPD).
  - Anteriormente, el prompt enviaba 4,534 tokens sin limitar `max_tokens`, por lo que 2 peticiones en un minuto superaban el cupo ITPM y disparaban 429.
  - Se fijó `max_tokens: 500` en las peticiones y se podó el prompt a ~1,150 tokens, permitiendo varias consultas por minuto dentro del cupo gratuito de Groq.

### 3. Poda de prompt a menos de 2000 tokens y desglose en log
- **Desglose de tokens en log**:
  - En cada interacción se desglosa el aporte de tokens de cada componente:
    `[tiempo] prompt_desglose alma={tok_alma} memoria={tok_memoria} perfil={tok_perfil} correcciones={tok_corr} historial={tok_hist} instrucciones={tok_inst} total={tok_total}`
    `[tiempo] prompt_tokens={tok_total} anterior={tokens_base} ahorro={ahorro}%`
- **Estrategia de poda (< 1,200 tokens totales, ahorro ~59%)**:
  - **Recuerdos relevantes**: Filtra `memoria.hechos` buscando coincidencia de palabras con el mensaje actual del usuario; selecciona máximo 3 hechos relevantes (o los 3 más recientes si no hay coincidencia).
  - **Acciones compactas**: Se depuran y acortan las descripciones de las más de 60 acciones del sistema a frases breves de hasta 50 caracteres, ahorrando más de 1,000 tokens.
  - **Historial reducido**: Se envían únicamente los últimos 4 turnos (`[-4:]`), recortando respuestas largas de Silvestra a 150 caracteres.
  - **Perfil y correcciones limitados**: Fragmentos concisos de máximo 250 caracteres cada uno.
  - **Fidelidad**: Se mantiene intacta la personalidad de Silvestra, español panameño, tono cálido y la **regla anti-invención estricta**.

## Modularización de Cerebro, Hora de Panamá, Memoria con Fechas y Recordatorios por Voz

### 1. Modularización de `cerebro.py`
Para mantener todos los archivos bajo el límite de 15 KB, `cerebro.py` se dividió limpiamente en tres módulos especializados manteniendo retrocompatibilidad total:
- **[cerebro_parser.py](file:///c:/Proyecto_Silvestra/cerebro_parser.py)** (~3.1 KB): Extracción y parseo de respuestas devueltas por modelos (`separar`, `_respuesta_parcial`, `_cortar`).
- **[cerebro_prompt.py](file:///c:/Proyecto_Silvestra/cerebro_prompt.py)** (~8.3 KB): Construcción del prompt del sistema, inyección de hora oficial de Panamá, selección semántica de recuerdos, compactación de acciones y desglose de tokens.
- **[cerebro.py](file:///c:/Proyecto_Silvestra/cerebro.py)** (~4.8 KB): Coordinador del historial de diálogo, envío a proveedores conmutables y reflexión periódica.

### 2. Hora y fecha reales de Panamá (`America/Panama`)
- Inyección en cada turno de conversación de la hora y fecha exactas obtenidas mediante `zoneinfo.ZoneInfo("America/Panama")`.
- Formato panameño natural de 12 horas con día de la semana en español (ej: *"Hoy es miércoles 18 de noviembre de 2026, 11:15 p. m."*).
- Regla estricta en el prompt: Silvestra nunca inventa la hora; si el usuario pregunta qué hora es o qué día es hoy, utiliza exactamente este dato oficial.
- Registro en log: `[hora] inyectada='...'`

### 3. Memoria permanente con fechas, categorías semánticas y extracción continua
- **Estructura modular (`memoria.py` ~14.3 KB, `memoria_busqueda.py` ~7.8 KB y `memoria_filtro.py` ~4.0 KB)**:
  - `memoria.py`: API principal (`recordar`, `olvidar`, `consultar`, `extraer_hechos_conversacion`), registro de acciones y persistencia en `memoria.json`.
  - `memoria_busqueda.py`: Motor de búsqueda semántica con normalización NFD, eliminación de stopwords, ponderación por recencia, mapeo categórico y resumen temático de recuerdos antiguos.
  - `memoria_filtro.py`: Validación de hechos, filtro estricto anti-meta (comandos, interfaz, pruebas, conjeturas) y desduplicación semántica por coincidencia de conceptos.
- **Registro duradero y con fecha**: Cada nuevo recuerdo o hecho importante sobre Moisés (gustos, personas, planes, proyectos) se registra con su fecha en `memoria.json` (ej: `[2026-11-19] hecho`).
- **Filtro de privacidad estricto**: Rechaza y nunca guarda contraseñas, tokens, claves, secretos, API keys o datos financieros sensibles (`PALABRAS_PRIVADAS`).
- **Extracción más completa en segundo plano (`extraer_hechos_conversacion`)**: Al terminar una sesión o cada 3 turnos de conversación, se lanza un hilo daemon secundario con prompt depurado anti-meta para extraer automáticamente hechos duraderos, desduplicarlos y persistirlos con fecha y filtro de privacidad.
- **Búsqueda semántica por categorías y sinónimos**: Mapeo inteligente en categorías (`familia`, `trabajo`, `comida`, `planes`, `proyectos`) y sinónimos para recuperar recuerdos relevantes aunque la pregunta use palabras distintas (ej. *"cenar"* encuentra recuerdos de *"pizza"*).
- **Memoria antigua resumida**: Al superar ~200 recuerdos, los hechos más antiguos se compactan en párrafos temáticos (`resumenes_tematicos`) sin perder conocimiento histórico ni sobrecargar el almacenamiento.
- **Comandos y acciones por voz**:
  - `guardar_recuerdo` (alias: `recuerda_esto`): Guarda hechos inmediatamente al decir *"recuerda esto: ..."*.
  - `consultar_memoria` (alias: `que_sabes`): Responde con honestidad estricta qué sabe de Moisés en general (*"qué sabes de mí"*) o sobre un tema específico (*"qué sabes de mi comida favorita"*). Si no hay recuerdos, admite honestamente que no sabe (sin inventar).
  - `olvidar`: Elimina recuerdos específicos o temas por voz (*"olvida lo de X"*).
- **Log unificado**: `[memoria] guardados=N relevantes=N total=N`.
- **Inyección semántica en el prompt**: Máximo 5 recuerdos más relevantes al mensaje actual, manteniendo el prompt total por debajo de 2,000 tokens (habitualmente entre 1,150 y 1,350 tokens).

### 4. Recordatorios y alarmas por voz (`recordatorios.py`)
- **Acciones registradas**:
  - `poner_recordatorio` (y alias `recordar`): Relativo (*"en 20 minutos"*, *"en 2 horas"*, *"en 30 segundos"*) o absoluto (*"mañana a las 8"*, *"a las 5:30 pm"*).
  - `listar_recordatorios`: Enumera los recordatorios pendientes activos con su hora exacta.
  - `cancelar_recordatorio`: Cancela un recordatorio por texto o tema.
- **Persistencia en `recordatorios.json`**: Los recordatorios sobreviven al reinicio de la aplicación.
- **Hilo secundario (`RecordatoriosLoop`)**: Revisa cada **1 segundo** sin bloquear la aplicación. Al vencer, envía un evento seguro a `app.cola` (`hablar_registro`) para que Silvestra hable y muestre la burbuja en la ventana principal Qt (cero llamadas directas a Qt desde hilos).
- **Aviso al arrancar**: Si Silvestra estuvo apagada y algún recordatorio venció mientras tanto, avisa inmediatamente al iniciar.
- **Confirmación hablada**: Cada recordatorio creado se confirma en voz alta indicando la hora exacta programada.
- **Registros en log**: `[recordatorio] creado='...' hora='...'`, `[recordatorio] disparado='...'`

## Interrupción al hablar (Barge-in), Respuestas Ágiles en Streaming y Rostro Vivo

### 1. Interrupción al hablar (Barge-in) con filtrado de eco
- **Corte instantáneo de voz (`voz.py`)**: Método `detener()` que incrementa la versión interna, detiene el reproductor pygame / proceso SAPI y limpia la cola de síntesis en menos de 10 ms.
- **Escucha continua y detección en tiempo real (`oido.py` / `conversacion.py`)**: Mientras Silvestra habla, el micrófono analiza bloques de 100 ms usando el reconocedor local Vosk.
- **Filtrado anti-eco y comandos de corte**: Compara las palabras detectadas con la salida actual (`_es_eco`). Si el usuario dice comandos claros (*"espera"*, *"ya"*, *"para"*, *"silencio"*, *"cállate"*, *"alto"*) o inicia una frase distinta, se corta el audio de inmediato y continúa escuchando al usuario para responder a lo nuevo.
- **Acción por voz**: `silencio` (alias: `para`, `callate`, `callar`) registrada con `acciones.registrar`.
- **Registro en log**: `[interrupcion] motivo=... tiempo_corte=...ms`

### 2. Respuestas más rápidas en streaming y medición de primera palabra
- **Extracción temprana de frases (`cerebro_parser.py`)**: Umbral de corte ajustado a 6 caracteres (`_cortar`) para emitir frases breves iniciales (*"¡Hola!"*, *"Claro."*) sin esperar al resto de la respuesta ni al cierre del bloque.
- **Canalización en segundo plano (`voz.py`)**: Mientras la primera frase se reproduce, la segunda se sintetiza en paralelo en un hilo secundario sin pausas ni cortes audibles.
- **Soporte robusto de etiquetas**: Parseo tolerante de respuestas directas y extracción de `EMOCION:` antes de `RESPUESTA:`.
- **Medición de latencia de primera palabra**: Registra el tiempo transcurrido desde el final de la voz del usuario hasta el primer sonido emitido:
  `[tiempo] primera_palabra=...s desde que terminé de hablar (anterior=...s, diff=...s)`.

### 3. Rostro vivo, seguimiento ocular y modularización (< 15 KB)
- **Modularización de interfaz**: Para cumplir la regla de 15 KB por archivo, `cara_qt.py` se separó en:
  - **[burbuja.py](file:///c:/Proyecto_Silvestra/burbuja.py)** (~1.7 KB): Widgets de burbuja flotante y diálogo de entrada.
  - **[cara_movimiento.py](file:///c:/Proyecto_Silvestra/cara_movimiento.py)** (~5.4 KB): `CaraMovimientoMixin` con paseo, ida a esquinas, seguimiento de mouse y baile.
  - **[cara_qt.py](file:///c:/Proyecto_Silvestra/cara_qt.py)** (~12.9 KB): Ventana principal Qt, timers de dibujo y eventos.
  - **[cara_dibujo.py](file:///c:/Proyecto_Silvestra/cara_dibujo.py)** (~12.4 KB): Renderizado visual con `QPainter` (siempre cerrado en `try: ... finally: p.end()`).
- **Seguimiento ocular con la cámara (`camara.py`)**: Detecta la posición normalizada del rostro del dueño (`ult_pos_rostro`) e interpola la mirada con factor de suavizado 0.09, logrando movimientos oculares sutiles, orgánicos y no bruscos.
- **Microexpresiones al escuchar y asentimiento**:
  - Inclinación curiosa de la cabeza cuando `self.escuchando` está activo.
  - Asentimiento suave (`asentir`) al terminar de oír al usuario.
  - Respiración sutil en reposo y parpadeo con variación aleatoria y probabilidad de doble parpadeo.
- **Contraste emocional vivo**: Mayor diferenciación visual en cejas, boca, rubor y color base entre las emociones (`alegre`, `preocupada`, `seria`, `calida`) con transiciones fluidas.
- **Regulación de FPS y bajo consumo de CPU**: En reposo reduce la tasa de refresco a 50 ms (~20 FPS) para ahorrar CPU. Registro cada 5 segundos:
  `[cara] fps=..., cpu_estimada=...%`.

### 4. Control de la Laptop por Niveles (Windows)
- **Módulos**: `control_seguridad.py` (~8.8 KB) y `control_laptop.py` (~14.4 KB).
- **Nivel LIBRE (sin código)**:
  - `apps_permitidas.json`: lista blanca editable de ejecutables (`chrome`, `edge`, `spotify`, `notepad`, `calculadora`, `word`, etc.).
  - `abrir_app` / `cerrar_app`: apertura y cierre controlado vía `subprocess` con lista de argumentos (sin `shell=True`). `cerrar_app` ejecuta `taskkill` sin `/F` primero y tiene prohibición estricta de cerrar procesos críticos (`python`, `code`, `antigravity`, `silvestra`, `main`).
  - `ir_a`: navegación a carpetas del sistema (Escritorio, Documentos, Descargas, Proyecto) y sitios web permitidos (YouTube, Google, Gmail, GitHub, Wikipedia), además de retorno a la ventana anterior con Alt+Tab (`ctypes`).
  - `musica_youtube`: respuesta hablada inmediata ("Poniendo música en YouTube...") sin esperar peticiones de red, búsqueda de `videoId` en segundo plano con `requests` y reproducción directa con autoplay. Incluye atenuación de volumen automática (audio ducking ~25%, `DUCKING_AUDIO`) mientras Silvestra habla o escucha, y filtro estricto de órdenes durante música (`VERIFICAR_DUENO_CON_MUSICA`) para evitar disparos falsos de Whisper o activación de "Listo, dejo de escuchar".
  - `multimedia`: subir/bajar volumen, silenciar, pausar/reanudar, siguiente/anterior canción con `keybd_event` de Windows, minimizar todo (Win+D), captura de pantalla con `PIL.ImageGrab` guardada en Escritorio y bloqueo de estación de trabajo con `LockWorkStation()`. Todo en hilos secundarios entregando resultados a `app.cola`.
- **Nivel CON CÓDIGO (exclusivo por Telegram)**:
  - Acciones peligrosas: `apagar_laptop`, `reiniciar_laptop`, `suspender_laptop`, `cerrar_sesion_laptop`.
  - Exclusividad Telegram: si se piden por voz o chat local, responde *"Eso solo puedo hacerlo por Telegram."* y no solicita código.
  - Validación de dueño en Telegram: únicamente se atienden si el `chat_id` coincide con `ID_TELEGRAM_DUENO` de `config.py`. Mensajes de terceros se ignoran en silencio y se registran en `acciones_log.txt` (solo ID y hora, sin el mensaje). Si `ID_TELEGRAM_DUENO` es 0 o falta, el bot no ejecuta acciones.
  - Desafío interactivo: Silvestra responde *"Dime el código."* y la siguiente frase se procesa localmente contra `CODIGO_SEGURIDAD` en `config.py`.
  - Entiende números hablados ("dos cero cero seis") y dígitos ("2006").
  - Máximo 3 intentos y caducidad de 30 segundos. Al fallar 3 veces se bloquea temporalmente por 60 segundos.
  - Privacidad total: el código de seguridad NUNCA se envía al LLM, ni a logs, ni a la memoria permanente.
- **Nivel PROHIBIDO (nunca)**:
  - Borrado de archivos, ejecución libre de comandos (cmd/powershell), instalación de paquetes o modificación de `config.py`, memoria o claves privadas. Se intercepta inmediatamente con rechazo explícito.
- **Registro de auditoría**:
  - `acciones_log.txt`: registra cada acción solicitada, nivel, origen, estado y detalle (sin registrar jamás el código).

### 5. Optimización de Latencia, VAD Adaptativo, Sincronización del Aro y Filtro de Falsos Disparos
- **Optimización de Latencia y Camino Crítico**:
  - **Caché en RAM para perfil de conversación (`aprendizaje_datos.py`)**: `resumen_para_prompt` leía `perfil_conversacion.json` de disco bajo bloqueo sincrónico en cada turno (~93.7 ms). Con caché en RAM basada en mtime/TTL, se redujo a **0.57 ms** (~93 ms ahorrados antes de llamar al LLM).
  - **VAD Adaptativo (`oido.py`)**: Si el usuario habló una frase completa (>0.8s) y la energía cae a nivel de ruido ambiente, la detección de fin de habla se corta a **0.45s** en vez de 0.55s (`VAD_ADAPTATIVO = True`), evitando cortes prematuros en pausas naturales.
  - **Muletillas de espera**: Desactivadas por defecto (`MULETILLAS_ACTIVAS = False`) para evitar cortes abruptos ("A ver...") mientras sintetiza Edge-TTS.
  - **Enrutamiento rápido en Groq**: Modelo `qwen/qwen3.8-27b` priorizado en `modelos_charla` (TTFT de 0.24-0.76s; primera frase en <0.85s).
- **Aro de la Cara Sincronizado (`cara_qt.py`, `conversacion.py`)**:
  - Al desactivar la escucha (por botón, comando "deja de escuchar", o timeout de silencio), se invoca `dejar_de_escuchar(app)` apagando `app.escuchando` y forzando `self.update()`, retornando de inmediato al color celeste (`CIAN`). Al escuchar, el aro pulsa en amarillo (`AMARILLO`).
- **Erradicación del Bucle de Falsos Disparos ("Te escucho" / "Listo, dejo de escuchar")**:
  - `palabra_clave.py` tenía una regla `p.startswith("sil") and len(p) >= 5` que confundía *"silencio"* con la palabra clave y relanzaba la conversación en un ciclo infinito.
  - Se añadieron `PALABRAS_EXCLUIDAS` (silencio, silenciosa, silaba, etc.) y prefijos estrictos (`silvest`, `sylvest`, `silvi`).
  - `alternar_conversacion` registra ahora el motivo explícito en el log: `[conversacion] alternar_conversacion motivo=... nuevo_estado=...`.

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
  - Datos personales de Moisés: `dueno.npy` (vector biométrico facial), `voz_dueno.npy` (biometría de voz), `memoria.json`, `correcciones.json`, `estado.json`, `diario.md`, `recordatorios.json`, `hilos.json`, `ideas.json`, `notas.json`, `conversaciones_dia.json`, `perfil_conversacion.json`.
  - Archivos pesados y generados: carpeta `modelos/`, `propuestas/`, `propuestas.json`, registros `silvestra.log`, base de datos `silvestra.db` y caché `__pycache__/`, `.venv/`.
- **Regla de oro de control de versiones:**
  - **Haz siempre un commit antes de pedir un cambio grande a Gemini / Antigravity**. De este modo, si alguna modificación rompe la estabilidad o no te gusta el resultado, podrás volver al estado anterior inmediatamente con un solo comando.

## Cómo trabajar en este proyecto
Una tarea a la vez. Antes de empezar: copia la carpeta como respaldo. Lee los archivos que vas a tocar. Haz el cambio mínimo. Pruébalo. Muestra qué cambió y cómo probarlo. Si algo no está claro, pregunta.