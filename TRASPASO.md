# TRASPASO — SILVESTRA

## Arquitectura y reglas
Asistente personal Python/Windows con avatar PySide6, voz/escucha, percepción y Context Engine, memoria cognitiva, planificación, permisos y ejecución supervisada. La UI solo se toca desde Qt; los hilos secundarios comunican mediante `app.cola`/señales. Máximo 15,360 B por `.py`; máximo 6,656 B aquí. No exponer claves ni tokens. Las inferencias no son hechos ni autorizan acciones. Toda operación sensible requiere aprobación y permisos centrales.

## Componentes
- `main.py`, `eventos.py`, `cara_*.py`: aplicación Qt, avatar y cola de eventos.
- `voz*.py`, `oido*.py`, `audio_*.py`: TTS, reproducción/RMS, captura y VAD.
- `cerebro*.py`, `respuesta_flujo.py`, `proveedores*.py`: conversación, prompt y proveedores.
- `memoria*.py`, `persistencia_segura.py`: memoria cognitiva SQLite/FTS5, formación, recuperación, grafo, linaje, consolidación y olvido por usuario.
- `contexto_*.py`, `multimodal_*.py`, `percepcion_*.py`, `vision_*.py`: contexto Windows y percepción pasiva; incertidumbre explícita, sin guardar capturas.
- `razonamiento_*.py`, `planificacion_*.py`, `experiencia_*.py`: razonamiento, planes y aprendizaje trazable; no altera código, seguridad o permisos.
- `ejecucion_*.py`, `permisos_*.py`, `acciones.py`: ejecución validada, permisos y registro de capacidades.
- `iniciativa*.py`, `recordatorios.py`, `telegram_*.py`, `pantalla_remota*.py`: iniciativa cancelable, recordatorios, Telegram y HUD tablet.

## Fases cerradas
- Fase 1: base de Silvestra, UI/voz, persistencia segura, Context Engine, iniciativa y planificador.
- Fase 2: ejecución supervisada, permisos, sandbox y operaciones seguras.
- Fase 3: percepción multimodal pasiva, visión/OCR, cámara y audio; fuentes privadas y desactivadas por defecto. Validación global; pruebas físicas pendientes.
- Fase 4: memoria cognitiva SQLite/FTS5, formación, recuperación, grafo, mantenimiento, olvido y razonamiento de solo lectura. Ventanas actuales separadas de recuerdos históricos.
- Fase 5: razonamiento, planificación y aprendizaje experiencial coordinados con ejecución/verificación. Requiere aprobación de plan, permisos y confirmación; aprendizaje no cambia políticas.
- Voz–cara: sincronía con reproducción real/RMS por generación en `cara_sincronia.py`; Qt solo renderiza.

## Fase 6 — Etapa 1
Contratos versionados y sanitizados (`ecosistema_contratos*.py`), seis tipos de dispositivo, sesiones/scopes fail-closed y observaciones no ejecutables. Pruebas con datos sintéticos.

## Fase 6 — Etapa 2 (cierre)
Integración segura del HUD y contratos del ecosistema. `ecosistema_almacen.py` mantiene un archivo independiente con reemplazo atómico; `ecosistema_gestor.py`/`ecosistema_sesiones.py` usan códigos de emparejamiento de un uso, hashes PBKDF2, sesiones expiran, latidos, revocación y scopes. El núcleo es único; clientes no reciben capacidades centrales. Cookies HttpOnly/SameSite; token y código no van en URL.

`ecosistema_puente.py` aplica allowlist de Origin, privacidad y separación Observation/CommandRequest/ApprovalRequest. Observaciones no ejecutan; operaciones van por `IntegracionCognitivaFase5`, `SistemaEjecucion` y `MotorPermisos`; aprobación en dispositivo autorizado y distinto al solicitante. Sin llamada remota directa a `acciones.ejecutar`.

`ecosistema_sse.py` ofrece replay con ID, buffer/conexiones/rate limit acotados y heartbeat. El servidor escucha solo loopback por defecto; acceso externo requiere TLS explícito y certificado válido. Modo privado filtra biometría, contexto, notas, recordatorios y telemetría personal antes de REST/SSE. Metadatos de dispositivo se conservan al entrar por `app.cola`. No se modifican los JSON de estado ni datos existentes; el almacén nuevo es `ecosistema_dispositivos.json`.

Suite: `test_ecosistema_integracion_fase6_etapa2.py`. Etapa cerrada; no iniciar Fase 7 sin instrucción del usuario.
