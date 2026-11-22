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
