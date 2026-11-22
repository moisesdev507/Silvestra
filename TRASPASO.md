# TRASPASO — LYRIS // SILVESTRA

## Arquitectura y reglas
Asistente modular Python/Windows con avatar PySide6, voz/escucha, Context Engine, memoria cognitiva, planificación y permisos supervisados. UI exclusiva desde Qt; hilos secundarios usan `app.cola`/señales. Límite: <= 15,360 B por `.py`; <= 6,656 B aquí. Inferencias no autorizan acciones; operaciones sensibles requieren confirmación.

## Componentes principales
- `main.py`, `eventos.py`, `cara_*.py`: aplicación Qt, avatar holográfico y eventos.
- `voz*.py`, `oido*.py`, `audio_*.py`: TTS, RMS, captura y VAD.
- `cerebro*.py`, `respuesta_flujo.py`, `proveedores*.py`: conversación, prompt e identidad Lyris.
- `cerebro_grafo.py`, `cerebro_planificador.py`, `cerebro_entrenamiento.py`: grafo vivo, multi-paso y auto-aprendizaje.
- `cerebro_trabajo.py`, `cerebro_proactivo.py`, `cerebro_mentor.py`: memoria corta, proactividad y modo mentora.
- `memoria*.py`, `persistencia_segura.py`, `cerebro_rag.py`: persistencia SQLite/FTS5, linaje y RAG seguro.
- `contexto_*.py`, `multimodal_*.py`, `vision_*.py`: percepción Windows, visión de pantalla y telemetría.
- `pantalla_remota*.py`, `ecosistema_*.py`, `app_movil_*.py`: HUD tablet, PWA móvil, SSE y LAN/Tailscale.
- `habilidades_archivos.py`, `aprendiz_habilidades.py`: archivos y habilidades con auditoría AST.

## Fases y Mejoras Consolidadas (Fase 1 a Fase 6)
1. **Identidad, HUD y LAN (`cara_*.py`, `pantalla_remota*.py`):** Cian/esmeralda calmado, HTTPS `0.0.0.0:8765`, orbe central, failover SSE a polling y botones táctiles >= 48px.
2. **Archivos seguros y calidad (`recordatorios.py`, `habilidades_archivos.py`):** Sin archivos vacíos, saneo de hashes/tokens y validación sintáctica.
3. **Cerebro sabio y auto-aprendizaje (`cerebro_grafo.py`, `cerebro_planificador.py`):** Grafo en SQLite con sobreescritura de datos obsoletos, planificador multi-paso sin alucinaciones y tolerancia a Whisper.
4. **Memoria de trabajo y proactividad (`cerebro_trabajo.py`, `cerebro_proactivo.py`):** Resolución de anáforas (*'léelo'*, *'agrégale'*), guardarraíles (15 min cooldown, Privado/Noche) y briefing diario.
5. **Autorización LAN y soporte Unicode (`ecosistema_eventos.py`, `cerebro_entrenamiento.py`):** Autorización directa para tablet/móvil LAN del dueño y soporte de tildes/`ñ` en propuestas.
6. **Cero atropello y ejecución local (`cerebro_proactivo.py`, `respuesta_flujo.py`):** Gracia inicial 15s, bloqueo si habla o hay audio en cola, y lecturas locales < 50ms.
7. **Habilidades reales, visión y RAG (`cerebro_entrenamiento.py`, `vision_pantalla.py`, `cerebro_rag.py`):** Código funcional real auditado por AST, visión en memoria Gemini REST y RAG SQLite FTS5.
8. **Modo Mentora socrática y expresiones (`cerebro_mentor.py`, `cara_emociones.py`, `presentacion.py`):** Directiva socrática compacta, presentación dinámica viva y emociones (`concentrada`, `firme`, `orgullosa`).
9. **App móvil PWA y Tailscale (`app_movil_*.py`, `pantalla_remota_api.py`):** Interfaz móvil en `/movil` estilo ChatGPT con avatar SVG dinámico, subred Tailscale CGNAT (`100.64.0.0/10`) y voz bidireccional.
10. **Memoria evolutiva, chat síncrono e íconos PWA (`memoria_sueno.py`, `memoria_progreso.py`, `memoria_asociativa.py`, `app_movil_*.py`):**
    - `memoria_sueno.py`: Deduplicación en reposo (Jaccard >= 0.82) y consolidación temática aditiva en `memoria_resumenes`.
    - `memoria_progreso.py`: Hitos técnicos, calibración socrática en `cerebro_mentor` y reporte de evolución como programador.
    - `memoria_asociativa.py`: Consulta unificada (resúmenes + grafo + RAG) en una sola llamada compacta (<= 600 chars).
    - `app_movil_*.py`: Endpoint síncrono `POST /api/movil/chat` e íconos PNG (`192x192` y `512x512`) generados con Pillow en memoria.
11. **Audio bidireccional móvil, UX rápida y certificado CA (`app_movil_audio.py`, `app_movil_html.py`, `app_movil_ui.py`):**
    - `app_movil_audio.py`: Endpoint `POST /api/movil/tts` para síntesis desacoplada MP3 en memoria (`mime: audio/mpeg`).
    - `app_movil_html.py`: Desbloqueo de audio en primer toque Android, indicador `"Lyris está pensando..."`, botón `🔊 Voz` y replay `🔊` en cada burbuja.
    - `app_movil_ui.py`: Descarga de certificado CA `hud_cert.pem` en `/movil/cert.pem` para instalación segura en Android.
12. **Blindaje proactivo/flujo y robustez móvil (`cerebro_proactivo.py`, `respuesta_flujo.py`):**
    - `cerebro_proactivo.py`: Atributo `ultimo_sueno_ts = 0.0` blindado en `MotorProactivo.__init__` y `evaluar_sueno_cognitivo`.
    - `respuesta_flujo.py`: Cierre post-respuesta protegido con `try/except` aislados para garantizar entrega y voz en laptop.
13. **Depuración de recordatorios, puerto 8765 único y audio TTS real (`recordatorios.py`, `app_movil_*.py`):**
    - `recordatorios.py`: `verificar_arranque` filtra recordatorios <= 24h, marca completados y persiste de inmediato. Suites de test aisladas con JSON temporal; `recordatorios.json` limpio y recuerdo 153 marcado obsoleto.
    - `app_movil_ui.py`: Eliminado puerto 8766; tráfico móvil unificado en HTTPS 8765 con barra de navegación limpia.
    - `app_movil_audio.py` y `app_movil_html.py`: TTS con filtro > 500 B y mock para tests; micro-WAV silencioso para desbloqueo síncrono de audio en Android Chrome.
14. **Saludo único acorde a la hora y captura de token en móvil (`nacimiento.py`, `cerebro_proactivo.py`, `app_movil_html.py`):**
    - `nacimiento.py` y `cerebro_proactivo.py`: Saludo único al encender según franja horaria real (mañana/tarde/noche); eliminada duplicación de briefing al arranque y cero mención a 'no tienes recordatorios'.
    - `app_movil_html.py`: Captura de `?token=...` en URL con guardado en `localStorage` y limpieza por `history.replaceState`; reintento automático con prompt de token ante HTTP 401.
15. **Persistencia de `remota_token` y autorización directa móvil (`pantalla_remota.py`, `pantalla_remota_api.py`, `pantalla_remota_accion.py`):**
    - `pantalla_remota.py`: Sincroniza y persiste `remota_token` desde/hacia `estado.json` al inicializar el servidor HUD.
    - `pantalla_remota_api.py`: Soporte para subred Tailscale IPv6 (`fd7a:115c:a1e0::/48`); validación segura con `hmac.compare_digest` contra `remota_token` en `POST /api/movil/*` y `GET /api/sesion` sin exigir previa sesión HUD/tablet.
    - `pantalla_remota_accion.py`: Despacho modular de acciones de panel HUD (`despachar_accion_panel`) manteniendo `pantalla_remota_api.py` en 14,179 B.
