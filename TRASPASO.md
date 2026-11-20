# TRASPASO DE PROYECTO — SILVESTRA

## 1. Quién es el dueño
- **Nombre:** Moisés (Panamá, `America/Panama`, español informal).
- **Perfil:** Principiante en programación (aprende sobre la marcha).
- **Comunicación:** Directo, párrafos cortos y explicaciones sencillas para teléfono móvil.

## 2. Metodología de trabajo
1. **Flujo de dos IAs:** IA planificadora redacta el prompt exacto; Moisés lo ejecuta en Gemini (Antigravity); Gemini entrega reporte conciso; Moisés reporta de vuelta.
2. **Reglas:** Honestidad técnica total, pruebas claras, commit previo y NUNCA pedir ni mostrar claves/tokens (`config.py`).

## 3. Silvestra y su arquitectura
Asistente personal con rostro interactivo PySide6, voz panameña (`es-PA-MargaritaNeural` / SAPI respaldo) y escucha con Whisper.

### Módulos principales
- **`main.py`**: Orquestación y ciclo principal PySide6.
- **`cara_*.py` / `baile_audio.py` / `burbuja.py`**: Avatar (208 px), mirada reactiva, inclinación, anillos HUD, 3 bailes y menú de confirmación 3s (`Renacer`/`Descansar`).
- **`naturalidad.py` / `correcciones.py`**: Continuidad conversacional (pausas <15m, 15m-3h, >3h) y autocorrección viva persistente (`correcciones.json`).
- **`oido*.py`**: Stream persistente anti-crash, Silero VAD, feedback WAV en memoria y Whisper/Vosk.
- **`voz*.py`**: Síntesis `edge-tts`, mixer thread-safe, RMS labial, corte barge-in y modulación emocional.
- **`cerebro*.py`**: Prompt optimizado (<1350 tok), carril dual (`rapido` vs `pro`), enrutador y acciones.
- **`proveedores*.py` / `sesion_http.py`**: Multi-LLM en cascada con pool Keep-Alive y streaming emocional temprano.
- **`memoria*.py`**: Memoria duradera con anclaje temporal, filtro anti-meta y extracción pasiva en voz.
- **`acciones.py`**: Registro central de capacidades del sistema (`acciones.registrar`).
- **`recordatorios.py` / `hilos.py`**: Recordatorios por voz e hilos con caducidad automática (>3 días).
- **`modos_sistema.py`**: 4 modos (`normal`, `programacion`, `estudio`, `noche`) en `estado.json` y HUD tablet.
- **`iniciativa.py`**: Comentarios espontáneos diurnos (7-23h) tras inactividad basados en hilos y memoria.
- **`telegram_puente*.py`**: Bot API nativo (`urllib.request` + SSL + IPv4) y llamadas asíncronas daemon sin bloqueos.
- **`control_*.py`**: Control por niveles (libre, peligroso con código y prohibido), VS Code y multimedia.
- **`contexto_*.py` / `iniciativa_contextual.py`**: Context Engine (Etapas 1-5): sensor Win32, motor 3 niveles, puente a prompt, telemetría SSE a tablet y motor de iniciativa contextual supervisable.
- **`pantalla_remota*.py` / `pantalla_biometria.py`**: HUD Jarvis tablet, telemetría y blindaje táctil de 3s.
- **`presencia.py` / `camara*.py`**: Detección facial YuNet + SFace multi-muestra (20 muestras) y enrolamiento.
- **`voz_dueno*.py`**: Biometría vocal CAM++ multi-muestra (25 muestras), scoring top-2 y Solo Dueño.
- **`respaldo.py`**: Copias zip fuera de Git (`~/Documents/Respaldos_Silvestra`) rotadas a 10 archivos.
- **`prueba_humo.py`**: Suite de validación de sintaxis, reglas de 15 KB y módulos clave.

### Reglas de oro de desarrollo
1. **Tamaño máximo:** Ningún archivo debe superar los **15 KB** (~15,360 bytes). TRASPASO.md <= 6.5 KB.
2. **Hilo principal Qt protegido:** Cero llamadas a Qt desde hilos secundarios (`app.cola` o señales).
3. **I/O en hilos secundarios:** Red, LLMs, TTS y procesos pesados siempre en hilos daemon.
4. **Acciones:** Toda capacidad se expone mediante `acciones.registrar(nombre, funcion, descripcion)`.
5. **Configuración y claves:** Exclusivamente en `config.py` (ignorado en git).

## 4. Estado actual (lo que ya funciona)
- Avatar PySide6 compacto (208 px), anillos reactivos y 3 bailes con música local.
- Doble confirmación de 3s en reinicio/despertar/renacer en menú y tablet HUD.
- Naturalidad y autocorrección viva (`naturalidad.py`, `correcciones.py`) con seguimiento de pausas.
- Interrupción por voz (barge-in <500ms), filtro de eco, Silero VAD neuronal y Vosk/Whisper offline.
- Personalidad panameña concisa (1-2 frases habladas, confirmaciones breves sin relleno).
- Prompt optimizado (<1350 tok) y pool Keep-Alive multi-LLM en cascada.
- Memoria duradera fechada, anclaje temporal, caducidad de hilos y extracción pasiva en segundo plano.
- Enrutador de dos carriles (`cerebro_enrutador.py`): `rapido` gratis vs `pro` con fallback.
- Control por niveles con código de seguridad y auditoría en Telegram.
- HUD Jarvis tablet con telemetría en vivo, switch Solo Dueño y selector de 4 modos.
- 4 modos (`normal`, `programacion`, `estudio`, `noche`) en `estado.json` y prompt dinámico.
- Biometría vocal CAM++ (25 muestras) y facial YuNet+SFace (20 muestras) con entrenamiento Telegram.
- Telegram 100% nativo (`urllib.request` + SSL + IPv4, <0.6s) sin timeouts ni bloqueos de Qt.
- Context Engine Etapas 1-5 (`contexto_*.py`, `iniciativa_contextual.py`): certeza 3 niveles, prompt <=50 tok, HUD tablet 5 tarjetas y motor de iniciativa contextual supervisable con cooldowns y revalidación.
- Iniciativa espontánea contextual activa (`iniciativa.py`) y modulación emocional viva desde el 1er token.
- Suite `prueba_humo.py` 100% PASS y arquitectura modular (todos los `.py` <= 15 KB).

## 5. Tareas pendientes y pospuestas
- [ ] **Rotar clave de Groq:** Clave expuesta en el pasado; rotar en `config.py` y Groq.
- [ ] **Cerebro premium ($5/mes):** Integrar proveedor de alta calidad con límite estricto de gasto.
- [ ] **Respaldo local:** Modelo SLM/LLM cuantizado local (Ollama / llama.cpp) 100% offline.
- [x] **Iniciativa propia:** Saludos o comentarios espontáneos en momentos oportunos (bucle de revisión diurna conectado).
- [ ] **Núcleo headless y nube:** Separar lógica para correr 24/7 en VPS conectada al bot de Telegram.
- [ ] **Anillo físico:** Pospuesto hasta contar con el hardware del anillo físico Bluetooth.

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

---
*Nota: Para detalles técnicos extensos, consulta siempre `PROYECTO.md`.*
