# TRASPASO DE PROYECTO — SILVESTRA

## 1. Quién es el dueño
- **Nombre:** Moisés.
- **Ubicación e idioma:** Panamá (`America/Panama`), español informal.
- **Nivel:** Principiante en programación (aprende sobre la marcha).
- **Comunicación:** Directo, párrafos cortos y explicaciones sencillas para teléfono móvil.

## 2. Metodología de trabajo
1. **Flujo de dos IAs:** La IA planificadora redacta el prompt exacto; Moisés lo ejecuta en Gemini (Antigravity); Gemini entrega reporte conciso; Moisés reporta de vuelta.
2. **Reglas:** Honestidad técnica total, pasos de prueba claros, commit previo a cambios y NUNCA pedir ni mostrar claves/tokens (`config.py`).

## 3. Silvestra y su arquitectura
Asistente personal con rostro interactivo PyQt5, voz panameña (`es-PA-MargaritaNeural` / SAPI de respaldo) y comprensión de audio con Whisper.

### Módulos principales
- **`main.py`**: Orquestación y ciclo principal PyQt5.
- **`cara_qt.py` / `cara_dibujo.py` / `cara_movimiento.py` / `burbuja.py`**: Rostro animado, mirada suave, microexpresiones y boca sincronizada.
- **`oido.py` / `oido_flujo.py` / `oido_vad.py` / `oido_feedback.py`**: Flujo persistente anti-crash 0xc0000374, Silero VAD neuronal, feedback sutil (~75ms WAV en memoria) y Whisper/Vosk.
- **`voz.py` / `voz_reproductor.py` / `voz_cache.py`**: Síntesis `edge-tts`, reproductor thread-safe SDL/mixer, RMS labial, corte rápido barge-in y caché.
- **`cerebro.py` / `cerebro_prompt.py` / `cerebro_enrutador.py`**: Prompt (<1350 tokens), enrutador dos carriles (`rapido` gratis vs `pro` OpenRouter/Claude con fallback) y acciones.
- **`proveedores.py` / `proveedores_cadenas.py` / `sesion_http.py`**: Multi-LLM en cascada con pool HTTP Keep-Alive persistente y cooldown.
- **`memoria.py` / `memoria_busqueda.py` / `memoria_tiempo.py`**: Memoria con anclaje temporal (`memoria_tiempo.py`), filtro anti-meta y regla anti-anacronismo.
- **`acciones.py`**: Registro central de acciones del sistema (`acciones.registrar`).
- **`recordatorios.py`**: Recordatorios por voz persistentes en disco (`recordatorios.json`).
- **`hilos.py`**: Hilos pendientes con anclaje temporal (`memoria_tiempo.py`) y caducidad automática (>3 días o fecha vencida).
- **`modos_sistema.py`**: 4 modos compuestos (`normal`, `programacion`, `estudio`, `noche`) persistentes en `estado.json`, voz y tablet HUD.
- **`control_laptop.py` / `control_seguridad.py` / `control_pc.py`**: Control de laptop por niveles (libre, con código y prohibido) y multimedia.
- **`pantalla_remota*.py` / `pantalla_biometria.py`**: Servidor, HUD Jarvis tablet, telemetría y panel biométrico/modos en vivo (Solo Dueño, Refuerzo y Modos).
- **`respaldo.py`**: Respaldo zip fuera de Git (`~/Documents/Respaldos_Silvestra`) con rotación a 10 archivos.
- **`presencia.py` / `camara.py` / `camara_dueno.py`**: Presencia y biometría facial SFace + YuNet con banco multi-muestra (hasta 20) y entrenamiento por Telegram.
- **`voz_dueno.py` / `voz_dueno_banco.py` / `voz_dueno_registro.py`**: Biometría vocal CAM++ con banco multi-muestra (hasta 25), scoring top-2 y modos de seguridad.
- **`prueba_humo.py`**: Suite de validación de sintaxis, reglas de 15 KB y módulos clave.

### Reglas de oro de desarrollo
1. **Tamaño máximo:** Ningún archivo debe superar los **15 KB** (~15,360 bytes). TRASPASO.md <= 8 KB.
2. **Hilo principal Qt protegido:** Cero llamadas a Qt desde hilos secundarios (`app.cola` o señales).
3. **I/O en hilos secundarios:** Red, LLMs, TTS y procesos pesados siempre en hilos daemon.
4. **Acciones:** Toda capacidad se expone mediante `acciones.registrar(nombre, funcion, descripcion)`.
5. **Configuración y claves:** Exclusivamente en `config.py` (ignorado en git).

## 4. Estado actual (lo que ya funciona)
- Rostro reactivo, mirada suave (`camara.py`), parpadeo y aro facial interactivo.
- Interrupción por voz (barge-in <500ms), filtro de eco y exclusión mutua de streams de audio (sin 0xc0000374).
- Silero VAD neuronal (`oido_vad.py`), feedback auditivo suave en memoria (`oido_feedback.py`), Whisper determinista y Vosk offline.
- Personalidad concisa y natural (1-2 frases habladas, sin preguntas de relleno de chatbot, confirmaciones breves en acciones).
- Eliminación de confirmaciones habladas duplicadas en `eventos.py` (mantiene alertas de error, lecturas informativas y disparos directos).
- Prompt optimizado (<1350 tokens) con inyección selectiva (`cerebro_categorias.py`) y multillm en cascada con Keep-Alive.
- Memoria duradera con fechas, filtro estricto anti-meta, anclaje temporal (`memoria_tiempo.py`, evita preguntar por eventos pasados), caducidad automática de hilos pendientes (`hilos.py`) y desduplicación semántica (`memoria_filtro.py`).
- Enrutador de dos carriles determinista (`cerebro_enrutador.py`): `rapido` gratuito (<1s) vs `pro` avanzado (OpenRouter/Claude con fallback transparente).
- Control de laptop por niveles (libre, peligroso exclusivo por Telegram con código y auditoría).
- Respaldo automático fuera de Git (`respaldo.py`) con rotación a 10 archivos sin claves.
- HUD Jarvis tablet a pantalla completa con control biométrico en vivo (`pantalla_biometria.py`): badge Dueño/Invitado/Espera, telemetría de voz y cara, botón táctil Solo Dueño, botón Reforzar voz y selector de 4 modos.
- 4 modos operativos (`modos_sistema.py`): `normal`, `programacion`, `estudio` y `noche`, activables por voz (`activar_modo`) o toque en tablet, con ajuste de volumen, VS Code, persistencia en `estado.json` y directiva dinámica en prompt.
- Biometría CAM++ multi-muestra (`voz_dueno*.py`, 25 muestras), rotación FIFO (8 anclas fijas), scoring top-2, modos Solo Dueño/Invitado y `reforzar_mi_voz`.
- Biometría facial SFace multi-muestra (`camara_dueno.py`, `camara.py`), banco hasta 20 fotos (4 anclas fijas), descarte duplicados (>0.94) y aprendizaje por Telegram.
- Suite de prueba de humo (`prueba_humo.py`) y arquitectura modular (todos los archivos <= 15 KB).

## 5. Tareas pendientes y pospuestas
- [ ] **Rotar clave de Groq:** Clave expuesta en el pasado; rotar en `config.py` y Groq.
- [ ] **Cerebro premium ($5/mes):** Integrar proveedor de alta calidad con límite estricto de gasto.
- [ ] **Respaldo local:** Modelo SLM/LLM cuantizado local (Ollama / llama.cpp) 100% offline.
- [ ] **Iniciativa propia:** Saludos o comentarios espontáneos en momentos oportunos.
- [ ] **Núcleo headless y nube:** Separar lógica para correr 24/7 en VPS conectada al bot de Telegram.
- [ ] **Anillo físico:** Pospuesto hasta contar con el hardware del anillo físico Bluetooth.

## 6. Guía de prompts para Gemini (Antigravity)
```text
Lee PROYECTO.md, TRASPASO.md y [archivos relevantes]. Haz git commit antes de empezar.
[Descripción clara y específica del cambio o corrección].
Reglas de oro:
- Archivos .py <= 15 KB (si crece, dividir en módulos) y TRASPASO.md <= 8 KB.
- Nada de llamadas Qt directas desde hilos secundarios (usa app.cola).
- Todo trabajo pesado o de red en hilos secundarios daemon.
- No pidas claves ni inventes datos; español de Panamá.
Al terminar, muestra cómo probarlo, tamaños exactos y actualiza PROYECTO.md y TRASPASO.md.
```

---
*Nota: Para detalles técnicos extensos, diagramas y lecciones aprendidas, consulta siempre `PROYECTO.md`.*
