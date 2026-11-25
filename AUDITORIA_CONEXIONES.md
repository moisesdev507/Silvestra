# Auditoría de conexiones y paridad de motores — Silvestra

**Fecha:** 25 de noviembre de 2026  
**Alcance:** 398 archivos `.py` al iniciar; 288 módulos no-test auditados con AST e importaciones (291 tras crear los 3 módulos nuevos).  
**Punto de entrada:** `main.py`.  
**Motores comparados:** motor clásico (`respuesta_flujo`, `conversacion`, `acciones`, `eventos`, `cerebro`, `agente_herramientas`) y Gemini Live (`live_motor`, `live_audio`, `live_herramientas`, `live_orquestador`, `gemini_live`).

## 1. Resumen ejecutivo

La auditoría encontró **36 módulos huérfanos** (ningún flujo activo los importaba) y una **paridad incompleta** entre Gemini Live y el motor clásico. Tras conectar `gui_ventanas` y `procesos_operaciones` en modo de solo lectura, quedan **34 huérfanos**. El hallazgo más importante: el motor clásico ya tenía visión de pantalla vía `vision_pantalla` (REST), pero **Gemini Live no tenía ninguna herramienta de pantalla, portapapeles, ventanas, procesos, HUD ni control multimedia**. Además, el prompt de Live se truncaba a 2.200 caracteres y cortaba la propia guía de herramientas, por lo que la autorización explícita nunca llegaba al modelo.

Tras esta misión:

- `revisar_pantalla` funciona en **ambos motores** con captura en memoria y `google-genai` multimodal, con respaldo REST.
- Live expone 7 herramientas nuevas: `revisar_pantalla`, `leer_portapapeles`, `listar_ventanas`, `ventana_activa`, `listar_procesos`, `activar_hud` y `control_multimedia`.
- El motor clásico usa el mismo puente (`capacidades_extra`) y registra `revisar_pantalla` como acción de voz.
- Se conectaron dos módulos huérfanos de alto valor: `gui_ventanas` y `procesos_operaciones`, en modo **solo lectura** y sin permisos destructivos.
- Todos los `.py` siguen por debajo de 15.360 bytes y `prueba_humo.py` termina con `EXIT=0` y **0 avisos**.

## 2. Metodología

1. Se construyó el grafo de importaciones con `ast` para los 288 módulos no-test (`prueba_*.py` y `test_*.py` excluidos).
2. Se calcularon cuatro conjuntos alcanzables:
   - `main`: todo lo que cuelga de `main.py`.
   - `clásico`: semillas `respuesta_flujo`, `conversacion`, `acciones`, `eventos`, `cerebro`, `planificador`, `agente_herramientas`, `memoria_adaptadores`, `cerebro_planificador`.
   - `live`: semillas `live_motor`, `live_audio`, `live_herramientas`, `live_orquestador`, `gemini_live`.
   - `huérfano`: no alcanzable desde `main` ni desde ninguno de los dos motores.
3. La clasificación estática se complementó con una **clasificación por capacidad expuesta**: un módulo puede estar importado por Live y no ofrecer su capacidad al usuario (por ejemplo, `portapapeles` estaba importado solo en el flujo clásico).
4. Se midieron todos los tamaños con `os.path.getsize` antes y después de cada cambio.

## 3. Conteos de la auditoría

| Categoría | Antes | Después | Significado |
|---|---:|---:|---|
| Conectado a ambos motores | 108 | 115 | Alcanzable desde el árbol clásico y desde el árbol Live. |
| Solo en motor clásico | 58 | 56 | Alcanzable desde el flujo clásico, ausente en Live. |
| Solo en Gemini Live | 0 | 0 | No había ningún módulo exclusivo de Live; todo Live era compartido. |
| Núcleo compartido de `main.py` | 86 | 86 | UI, percepción, persistencia, ecosistema y composición; no son capacidades de un motor concreto. |
| Huérfano / desconectado | 36 | 34 | Existía en disco, pero ningún flujo activo lo importaba. |
| **Total analizado** | **288** | **291** | 288 módulos previos + 3 módulos nuevos de esta misión. |

> Nota: la categoría “Núcleo compartido de `main.py`” se añade para no mentir clasificando como “ambos motores” módulos que solo forman parte del proceso principal (por ejemplo `cara_qt`, `persistencia_segura` o `pantalla_remota`).

## 4. Paridad por capacidad (antes → ahora)

| Capacidad | Motor clásico antes | Gemini Live antes | Estado ahora |
|---|---|---|---|
| Ver / revisar pantalla | `vision_pantalla` (REST, solo texto) | No existía | `revisar_pantalla` compartida con `google-genai` + respaldo REST. |
| Portapapeles | `portapapeles` como contexto para el LLM | No existía | `leer_portapapeles` en ambos. |
| Ventanas abiertas / activa | No (dependía de módulos huérfanos) | No existía | `listar_ventanas` y `ventana_activa` en ambos, solo lectura. |
| Procesos activos | No (dependía de módulos huérfanos) | No existía | `listar_procesos` en ambos, solo lectura. |
| HUD / tablet | `pantalla_remota_accion` | Solo si el modelo acertaba la acción exacta | `activar_hud` explícita en ambos. |
| Multimedia | Volumen, música y pausa/siguiente vía `control_laptop` | Solo volumen y música | `control_multimedia` (pausa, reanudar, siguiente, anterior) en ambos. |
| Correo / calendario | `google_workspace` | `ejecutar_accion_pc` | Ambos. |
| Recordatorios | `recordatorios` | `ejecutar_accion_pc` | Ambos. |
| Archivos | `habilidades_archivos` | `ejecutar_accion_pc` | Ambos. |
| Apps permitidas | `control_laptop` | `ejecutar_accion_pc` | Ambos. |
| Clima / búsqueda web | `consulta_web` | `consultar_clima` y `buscar_en_internet` | Ambos. |
| Telemetría | `telemetria` | `consultar_estado_pc` | Ambos. |

## 5. Huérfanos: veredicto

### 5.1 Conectados en esta misión

| Módulo | Bytes | Cómo quedó conectado |
|---|---:|---|
| `gui_ventanas` | 5.362 | `capacidades_extra` lo usa para `listar_ventanas` y `ventana_activa`, con catálogo vacío y supervisor propio: solo lectura, sin enfocar ni cerrar ventanas. |
| `procesos_operaciones` | 12.936 | `capacidades_extra` usa `consultar_procesos` con `SupervisorProcesosSilvestra()`: solo enumeración, sin iniciar ni cerrar procesos. |

### 5.2 Huérfanos internos que no deben exponerse por voz

| Grupo | Módulos | Motivo |
|---|---|---|
| Pipeline visual de bajo nivel | `vision_imagen`, `vision_modelo`, `vision_motor`, `vision_ocr`, `vision_proveedores` | Son motores internos de comprensión/OCR; la voz usa la fachada `vision_compartida`/`vision_pantalla`. |
| Comprensión de interfaces | `ui_visual_analizador`, `ui_visual_comparador`, `ui_visual_modelo`, `ui_visual_motor` | Requieren el motor de ejecución y permisos; no son acciones de voz directas. |
| Registro de herramientas | `archivos_herramientas`, `archivos_operaciones`, `gui_herramientas`, `gui_inspeccion`, `gui_interaccion`, `gui_secuencias`, `procesos_herramientas` | Están diseñados para `motor_ejecucion` y `permisos_modelo`; exponerlos sin ese contrato permitiría acciones destructivas. |
| Motor de ejecución | `motor_ejecucion`, `motor_ejecucion_control`, `motor_ejecucion_estado` | Requiere `motor_permisos`; no se activa por voz sin autorización explícita. |
| Autonomía | `autonomia_modelo`, `autonomia_puente`, `orquestador_autonomia` | Subsistema de autonomía todavía no integrado al ciclo de voz. |
| Cámara | `camara_comparador`, `camara_contexto_temporal`, `camara_percepcion_modelo`, `camara_percepcion_motor` | Percepción pasiva de cámara; `camara.py` ya cubre la ruta activa. |
| Audio | `oido_feedback`, `oido_stream` | Componentes de streaming de audio de bajo nivel. |
| HUD interno | `pantalla_remota_panel`, `pantalla_remota_web` | Piezas internas del servidor HUD; la acción pública es `pantalla_remota_accion`. |
| Utilidades | `bajar_modelos`, `invocacion_pruebas`, `cara_preview` | Herramientas de desarrollo o previsualización, no capacidades del asistente. |
| Percepción | `percepcion_motor` | Motor de percepción de alto nivel; se alimenta desde `main.py`, no desde la voz. |

## 6. Cambios aplicados

En Gemini Live el análisis visual se devuelve como `FunctionResponse` de texto desde un hilo (`run_in_executor`); no se envía el JPEG crudo por `send_realtime_input`. Esa decisión evita el error WebSocket 1007 por payloads grandes y mantiene el audio libre de bloqueos.

| Archivo | Cambio | Bytes |
|---|---|---:|
| `vision_compartida.py` | **Nuevo.** Visión de pantalla con `google-genai`, captura en memoria, modo privado, timeout en hilo daemon y respaldo REST. | 4.620 |
| `capacidades_extra.py` | **Nuevo.** Puente compartido: pantalla, portapapeles, ventanas, procesos, HUD y multimedia. | 7.577 |
| `live_herramientas_extra.py` | **Nuevo.** Declaraciones y despacho asíncrono de las 7 herramientas Live nuevas. | 5.069 |
| `live_herramientas.py` | Fusiona declaraciones extra, despacha herramientas extra, detecta órdenes por texto y degrada con elegancia si el volumen falla. | 14.157 |
| `live_audio.py` | Autorización explícita de `revisar_pantalla` en el prompt normal y en el de arranque rápido; tope de prompt subido a 3.200 para no truncar la guía. | 13.127 |
| `acciones.py` | Registra `revisar_pantalla`; las teclas de volumen usan `ctypes` en vez de PowerShell. | 15.149 |
| `respuesta_flujo.py` | El flujo clásico pasa por `capacidades_extra`; se eliminó el bloque HUD duplicado. | 14.912 |
| `cerebro_categorias.py` | Categoriza `revisar_pantalla` dentro de “pantalla”. | 8.013 |
| `prueba_auditoria_herramientas.py` | **Nuevo.** 13 pruebas de visión, declaraciones, despacho y acciones clásicas. | 5.243 |

## 7. Verificación

| Prueba | Resultado |
|---|---|
| `prueba_auditoria_herramientas.py` | 13 pruebas OK. |
| `prueba_live_unificado.py` | 16 pruebas OK, `EXIT=0`. |
| `prueba_optimizacion_latencia.py` | 3 pruebas OK, `EXIT=0`. |
| `prueba_optimizaciones_voz.py` | 4 pruebas OK, `EXIT=0`. |
| `prueba_humo.py` | `EXIT=0`, 0 avisos, 398 archivos `.py` verificados. |
| Tamaño máximo | `invocacion_lyris.py` con 15.343 bytes; **ningún** `.py` supera 15.360. |

## 8. Clasificación completa de módulos

La tabla siguiente se genera con el mismo grafo AST usado en la auditoría. La columna “Categoría” usa las cinco categorías explicadas en la sección 3.

| Módulo | Bytes | Categoría | Nota |
|---|---:|---|---|
| `acciones` | 15.149 | Ambos motores | — |
| `aprendiz_habilidades` | 14.392 | Ambos motores | — |
| `audio_lock` | 444 | Ambos motores | — |
| `busqueda_web` | 4.837 | Ambos motores | — |
| `calidad_respuesta` | 6.152 | Ambos motores | — |
| `camara_dueno` | 7.298 | Ambos motores | — |
| `capacidades_extra` | 7.577 | Ambos motores | — |
| `cara_holo_3d` | 10.541 | Ambos motores | — |
| `cara_orbe_hibrido` | 13.362 | Ambos motores | — |
| `cara_sincronia` | 4.520 | Ambos motores | — |
| `cerebro_categorias` | 8.013 | Ambos motores | — |
| `cerebro_parser` | 8.701 | Ambos motores | — |
| `cerebro_perfil` | 4.997 | Ambos motores | — |
| `cerebro_trabajo` | 6.545 | Ambos motores | — |
| `config` | 10.998 | Ambos motores | — |
| `consulta_web` | 9.448 | Ambos motores | — |
| `contexto_hud` | 6.071 | Ambos motores | — |
| `contexto_motor` | 14.114 | Ambos motores | — |
| `contexto_reglas` | 7.436 | Ambos motores | — |
| `contexto_windows` | 13.391 | Ambos motores | — |
| `control_laptop` | 15.162 | Ambos motores | — |
| `control_pc` | 9.321 | Ambos motores | — |
| `control_seguridad` | 9.673 | Ambos motores | — |
| `correcciones` | 7.942 | Ambos motores | — |
| `cuidado` | 10.945 | Ambos motores | — |
| `diario` | 9.932 | Ambos motores | — |
| `enrutador_expertos` | 8.942 | Ambos motores | — |
| `escenario_anillo` | 9.700 | Ambos motores | — |
| `escenario_escenas` | 7.894 | Ambos motores | — |
| `escenario_estilo` | 4.041 | Ambos motores | — |
| `escenario_paneles` | 10.191 | Ambos motores | — |
| `estado` | 1.859 | Ambos motores | — |
| `gemini_live` | 7.122 | Ambos motores | — |
| `google_workspace` | 9.656 | Ambos motores | — |
| `google_workspace_oauth` | 4.993 | Ambos motores | — |
| `gui_seguridad` | 4.792 | Ambos motores | — |
| `gui_ventanas` | 5.362 | Ambos motores | Conectado ahora (solo lectura) vía capacidades_extra. |
| `habilidades_archivos` | 9.128 | Ambos motores | — |
| `habla_espontanea` | 6.137 | Ambos motores | — |
| `hilos` | 5.588 | Ambos motores | — |
| `ideas` | 1.594 | Ambos motores | — |
| `iniciativa_kaya` | 9.056 | Ambos motores | — |
| `live_audio` | 13.127 | Ambos motores | — |
| `live_herramientas` | 14.157 | Ambos motores | — |
| `live_herramientas_extra` | 5.069 | Ambos motores | — |
| `live_motor` | 14.707 | Ambos motores | — |
| `live_orquestador` | 8.054 | Ambos motores | — |
| `memoria` | 13.535 | Ambos motores | — |
| `memoria_adaptadores` | 7.971 | Ambos motores | — |
| `memoria_almacen` | 11.129 | Ambos motores | — |
| `memoria_almacen_purga` | 1.536 | Ambos motores | — |
| `memoria_busqueda` | 7.791 | Ambos motores | — |
| `memoria_cache_rapida` | 2.463 | Ambos motores | — |
| `memoria_consolidacion` | 3.972 | Ambos motores | — |
| `memoria_consolidacion_validacion` | 2.194 | Ambos motores | — |
| `memoria_consulta` | 2.420 | Ambos motores | — |
| `memoria_esquema` | 3.757 | Ambos motores | — |
| `memoria_esquema_relaciones` | 5.341 | Ambos motores | — |
| `memoria_facade_mantenimiento` | 1.651 | Ambos motores | — |
| `memoria_filtro` | 5.479 | Ambos motores | — |
| `memoria_formacion` | 6.048 | Ambos motores | — |
| `memoria_gestor` | 7.074 | Ambos motores | — |
| `memoria_grafo` | 7.930 | Ambos motores | — |
| `memoria_grafo_recorrido` | 2.687 | Ambos motores | — |
| `memoria_grafo_utils` | 297 | Ambos motores | — |
| `memoria_migrador` | 3.156 | Ambos motores | — |
| `memoria_modelos` | 3.582 | Ambos motores | — |
| `memoria_olvido` | 2.134 | Ambos motores | — |
| `memoria_persistente` | 10.055 | Ambos motores | — |
| `memoria_politicas` | 2.055 | Ambos motores | — |
| `memoria_razonamiento` | 10.436 | Ambos motores | — |
| `memoria_razonamiento_evidencia` | 2.173 | Ambos motores | — |
| `memoria_razonamiento_grafo` | 3.014 | Ambos motores | — |
| `memoria_recuperacion` | 8.405 | Ambos motores | — |
| `memoria_relaciones` | 7.561 | Ambos motores | — |
| `memoria_semantica` | 7.621 | Ambos motores | — |
| `memoria_tema` | 3.104 | Ambos motores | — |
| `memoria_tiempo` | 5.846 | Ambos motores | — |
| `memoria_transacciones` | 2.458 | Ambos motores | — |
| `modos_rutina` | 3.682 | Ambos motores | — |
| `modos_sistema` | 6.728 | Ambos motores | — |
| `naturalidad` | 4.521 | Ambos motores | — |
| `pantalla` | 5.657 | Ambos motores | — |
| `pantalla_biometria` | 5.030 | Ambos motores | — |
| `pantalla_remota_accion` | 6.623 | Ambos motores | — |
| `pantalla_remota_datos` | 9.540 | Ambos motores | — |
| `persistencia_segura` | 2.118 | Ambos motores | — |
| `portapapeles` | 3.602 | Ambos motores | — |
| `procesos_operaciones` | 12.936 | Ambos motores | Conectado ahora (solo lectura) vía capacidades_extra. |
| `procesos_seguridad` | 7.104 | Ambos motores | — |
| `propuestas` | 15.054 | Ambos motores | — |
| `propuestas_prompt` | 11.640 | Ambos motores | — |
| `proveedores` | 8.458 | Ambos motores | — |
| `proveedores_cadenas` | 15.010 | Ambos motores | — |
| `proveedores_estado` | 4.163 | Ambos motores | — |
| `proveedores_stream` | 13.873 | Ambos motores | — |
| `proveedores_validador` | 5.172 | Ambos motores | — |
| `recordatorios` | 13.268 | Ambos motores | — |
| `respaldo` | 5.914 | Ambos motores | — |
| `sandbox_calculo` | 9.441 | Ambos motores | — |
| `sesion_http` | 806 | Ambos motores | — |
| `telegram_medios` | 10.841 | Ambos motores | — |
| `telegram_medios_proc` | 7.754 | Ambos motores | — |
| `telegram_puente` | 14.881 | Ambos motores | — |
| `telemetria` | 8.290 | Ambos motores | — |
| `tts_aura_stream` | 9.324 | Ambos motores | — |
| `vision_compartida` | 4.620 | Ambos motores | — |
| `vision_pantalla` | 7.163 | Ambos motores | — |
| `voz` | 14.972 | Ambos motores | — |
| `voz_cache` | 2.551 | Ambos motores | — |
| `voz_estilo` | 2.589 | Ambos motores | — |
| `voz_fonemas` | 1.928 | Ambos motores | — |
| `voz_local` | 6.115 | Ambos motores | — |
| `voz_rapida` | 3.547 | Ambos motores | — |
| `voz_reproductor` | 5.374 | Ambos motores | — |
| `agente_herramientas` | 10.051 | Solo motor clásico | — |
| `aprendizaje` | 15.146 | Solo motor clásico | — |
| `aprendizaje_datos` | 15.276 | Solo motor clásico | — |
| `baile_audio` | 11.038 | Solo motor clásico | — |
| `casa` | 6.263 | Solo motor clásico | — |
| `cerebro` | 15.099 | Solo motor clásico | — |
| `cerebro_enrutador` | 13.970 | Solo motor clásico | — |
| `cerebro_entrenamiento` | 12.898 | Solo motor clásico | — |
| `cerebro_estilo` | 1.498 | Solo motor clásico | — |
| `cerebro_grafo` | 7.781 | Solo motor clásico | — |
| `cerebro_mentor` | 8.194 | Solo motor clásico | — |
| `cerebro_planificador` | 10.048 | Solo motor clásico | — |
| `cerebro_prompt` | 13.664 | Solo motor clásico | — |
| `cerebro_rag` | 11.086 | Solo motor clásico | — |
| `charla_continua` | 6.899 | Solo motor clásico | — |
| `contexto_prompt` | 4.833 | Solo motor clásico | — |
| `conversacion` | 15.067 | Solo motor clásico | — |
| `dev_copiloto` | 8.592 | Solo motor clásico | — |
| `ecosistema_eventos` | 3.465 | Solo motor clásico | — |
| `ejecucion_modelo` | 8.307 | Solo motor clásico | — |
| `eventos` | 15.150 | Solo motor clásico | — |
| `eventos_rearme` | 1.962 | Solo motor clásico | — |
| `eventos_voz` | 2.184 | Solo motor clásico | — |
| `experiencia_almacen` | 4.029 | Solo motor clásico | — |
| `experiencia_analizador` | 1.787 | Solo motor clásico | — |
| `experiencia_esquema` | 2.649 | Solo motor clásico | — |
| `experiencia_modelos` | 2.631 | Solo motor clásico | — |
| `experiencia_motor` | 7.463 | Solo motor clásico | — |
| `identidad_kaya` | 6.075 | Solo motor clásico | — |
| `invocacion_lyris` | 15.343 | Solo motor clásico | — |
| `memoria_asociativa` | 3.514 | Solo motor clásico | — |
| `memoria_progreso` | 7.276 | Solo motor clásico | — |
| `memoria_sueno` | 9.788 | Solo motor clásico | — |
| `micro_voz` | 1.275 | Solo motor clásico | — |
| `oido_adaptacion` | 3.873 | Solo motor clásico | — |
| `oido_filtro` | 3.086 | Solo motor clásico | — |
| `planificacion_adaptativa` | 5.172 | Solo motor clásico | — |
| `planificacion_almacen` | 4.750 | Solo motor clásico | — |
| `planificacion_evaluador` | 7.171 | Solo motor clásico | — |
| `planificacion_modelos` | 4.327 | Solo motor clásico | — |
| `planificacion_motor` | 8.947 | Solo motor clásico | — |
| `planificador` | 14.485 | Solo motor clásico | — |
| `planificador_modelo` | 14.232 | Solo motor clásico | — |
| `presentacion` | 13.635 | Solo motor clásico | — |
| `qt_estabilidad_ui` | 3.834 | Solo motor clásico | — |
| `razonamiento_evaluador` | 5.826 | Solo motor clásico | — |
| `razonamiento_fuentes` | 2.394 | Solo motor clásico | — |
| `razonamiento_modelos` | 3.469 | Solo motor clásico | — |
| `razonamiento_motor` | 6.166 | Solo motor clásico | — |
| `respuesta_flujo` | 14.912 | Solo motor clásico | — |
| `sonidos_ui` | 1.309 | Solo motor clásico | — |
| `vigilante_proactivo` | 4.573 | Solo motor clásico | — |
| `voz_dueno` | 14.762 | Solo motor clásico | — |
| `voz_dueno_banco` | 7.782 | Solo motor clásico | — |
| `voz_dueno_registro` | 13.782 | Solo motor clásico | — |
| `voz_stream` | 3.765 | Solo motor clásico | — |
| `app_movil_audio` | 10.680 | Núcleo main | — |
| `app_movil_html` | 7.069 | Núcleo main | — |
| `app_movil_js` | 13.294 | Núcleo main | — |
| `app_movil_ui` | 6.466 | Núcleo main | — |
| `archivos_seguridad` | 6.514 | Núcleo main | — |
| `audio_clasificador` | 6.844 | Núcleo main | — |
| `audio_contexto_temporal` | 3.599 | Núcleo main | — |
| `audio_evento_modelo` | 3.718 | Núcleo main | — |
| `audio_percepcion_motor` | 8.006 | Núcleo main | — |
| `briefing_proactivo` | 5.940 | Núcleo main | — |
| `burbuja` | 1.714 | Núcleo main | — |
| `camara` | 14.337 | Núcleo main | — |
| `cara_baile` | 8.410 | Núcleo main | — |
| `cara_destello` | 1.182 | Núcleo main | — |
| `cara_dibujo` | 2.751 | Núcleo main | — |
| `cara_emociones` | 3.188 | Núcleo main | — |
| `cara_movimiento` | 8.435 | Núcleo main | — |
| `cara_nucleo` | 14.762 | Núcleo main | — |
| `cara_qt` | 15.276 | Núcleo main | — |
| `cerebro_proactivo` | 12.330 | Núcleo main | — |
| `ecosistema_almacen` | 2.687 | Núcleo main | — |
| `ecosistema_contratos` | 371 | Núcleo main | — |
| `ecosistema_contratos_base` | 4.077 | Núcleo main | — |
| `ecosistema_contratos_mensajes` | 3.086 | Núcleo main | — |
| `ecosistema_contratos_registro` | 3.480 | Núcleo main | — |
| `ecosistema_gestor` | 8.830 | Núcleo main | — |
| `ecosistema_puente` | 9.144 | Núcleo main | — |
| `ecosistema_qr_tls` | 1.371 | Núcleo main | — |
| `ecosistema_sesiones` | 7.173 | Núcleo main | — |
| `ecosistema_sse` | 4.680 | Núcleo main | — |
| `ejecucion_acciones` | 2.839 | Núcleo main | — |
| `ejecucion_esquemas` | 2.260 | Núcleo main | — |
| `ejecucion_registro` | 13.445 | Núcleo main | — |
| `escenario` | 8.919 | Núcleo main | — |
| `escenario_fondo` | 5.116 | Núcleo main | — |
| `escenario_intro` | 4.101 | Núcleo main | — |
| `escenario_nodos` | 3.327 | Núcleo main | — |
| `estudio` | 13.853 | Núcleo main | — |
| `experiencia_integracion` | 3.625 | Núcleo main | — |
| `habilidades` | 7.414 | Núcleo main | — |
| `hud` | 9.348 | Núcleo main | — |
| `hud_orbe` | 6.079 | Núcleo main | — |
| `iniciativa` | 6.129 | Núcleo main | — |
| `iniciativa_contextual` | 14.998 | Núcleo main | — |
| `integracion_cognitiva_fase5` | 3.568 | Núcleo main | — |
| `main` | 14.419 | Núcleo main | — |
| `menu_hud` | 9.244 | Núcleo main | — |
| `multimodal_correlacionador` | 3.246 | Núcleo main | — |
| `multimodal_integracion_modelo` | 6.115 | Núcleo main | — |
| `multimodal_integracion_motor` | 13.537 | Núcleo main | — |
| `multimodal_puente_app` | 13.180 | Núcleo main | — |
| `multimodal_ventana_win32` | 4.038 | Núcleo main | — |
| `nacimiento` | 4.879 | Núcleo main | — |
| `oido` | 14.926 | Núcleo main | — |
| `oido_deepgram` | 5.260 | Núcleo main | — |
| `oido_flujo` | 10.656 | Núcleo main | — |
| `oido_vad` | 8.851 | Núcleo main | — |
| `palabra_clave` | 10.655 | Núcleo main | — |
| `pantalla_remota` | 15.053 | Núcleo main | — |
| `pantalla_remota_api` | 14.527 | Núcleo main | — |
| `pantalla_remota_cliente_aux` | 4.373 | Núcleo main | — |
| `pantalla_remota_contexto_ui` | 7.530 | Núcleo main | — |
| `pantalla_remota_estilos` | 13.976 | Núcleo main | — |
| `pantalla_remota_js` | 12.129 | Núcleo main | — |
| `pantalla_remota_js_bio` | 6.459 | Núcleo main | — |
| `pantalla_remota_qr` | 4.987 | Núcleo main | — |
| `pantalla_remota_tema` | 7.594 | Núcleo main | — |
| `pantalla_remota_ui` | 9.719 | Núcleo main | — |
| `percepcion_adaptadores` | 6.744 | Núcleo main | — |
| `percepcion_modelo` | 4.570 | Núcleo main | — |
| `permisos_auditoria` | 3.463 | Núcleo main | — |
| `permisos_autorizaciones` | 6.405 | Núcleo main | — |
| `permisos_modelo` | 7.811 | Núcleo main | — |
| `permisos_motor` | 10.915 | Núcleo main | — |
| `presencia` | 7.802 | Núcleo main | — |
| `resumen` | 9.147 | Núcleo main | — |
| `resumen_media` | 4.506 | Núcleo main | — |
| `resumen_web` | 6.122 | Núcleo main | — |
| `saludo_dinamico` | 12.656 | Núcleo main | — |
| `situacion_evaluador` | 4.733 | Núcleo main | — |
| `situacion_interpretacion_modelo` | 5.023 | Núcleo main | — |
| `situacion_interpretacion_motor` | 8.808 | Núcleo main | — |
| `situacion_memoria_temporal` | 4.326 | Núcleo main | — |
| `verificacion_estrategias` | 5.306 | Núcleo main | — |
| `verificacion_modelo` | 6.043 | Núcleo main | — |
| `verificacion_motor` | 14.984 | Núcleo main | — |
| `archivos_herramientas` | 5.310 | Huérfano / desconectado | Registro para motor_ejecucion; no exponer sin permisos. |
| `archivos_operaciones` | 11.180 | Huérfano / desconectado | Operaciones de archivos con sandbox; no exponer sin contrato. |
| `autonomia_modelo` | 5.837 | Huérfano / desconectado | Modelos del subsistema de autonomía. |
| `autonomia_puente` | 3.600 | Huérfano / desconectado | Puente del subsistema de autonomía. |
| `bajar_modelos` | 5.229 | Huérfano / desconectado | Utilidad de descarga de modelos. |
| `camara_comparador` | 4.270 | Huérfano / desconectado | Comparador de percepción de cámara. |
| `camara_contexto_temporal` | 2.592 | Huérfano / desconectado | Contexto temporal de cámara. |
| `camara_percepcion_modelo` | 3.747 | Huérfano / desconectado | Modelos de percepción de cámara. |
| `camara_percepcion_motor` | 9.805 | Huérfano / desconectado | Motor de percepción de cámara. |
| `cara_preview` | 6.989 | Huérfano / desconectado | Previsualización de la cara; herramienta de desarrollo. |
| `gui_herramientas` | 5.525 | Huérfano / desconectado | Registro GUI para motor_ejecucion; requiere permisos. |
| `gui_inspeccion` | 4.682 | Huérfano / desconectado | Inspección de controles GUI; requiere autorización. |
| `gui_interaccion` | 4.444 | Huérfano / desconectado | Interacción con controles GUI; requiere autorización. |
| `gui_secuencias` | 2.270 | Huérfano / desconectado | Secuencias GUI; requieren autorización. |
| `invocacion_pruebas` | 2.204 | Huérfano / desconectado | Utilidad de pruebas de invocación. |
| `motor_ejecucion` | 13.436 | Huérfano / desconectado | Motor de tareas con permisos; no se activa por voz directa. |
| `motor_ejecucion_control` | 6.614 | Huérfano / desconectado | Control del motor de ejecución. |
| `motor_ejecucion_estado` | 6.099 | Huérfano / desconectado | Estados y colas del motor de ejecución. |
| `oido_feedback` | 2.794 | Huérfano / desconectado | Feedback de audio de bajo nivel. |
| `oido_stream` | 4.417 | Huérfano / desconectado | Streaming de audio de bajo nivel. |
| `orquestador_autonomia` | 13.242 | Huérfano / desconectado | Orquestador de autonomía aún no integrado. |
| `pantalla_remota_panel` | 5.735 | Huérfano / desconectado | Pieza interna del panel HUD. |
| `pantalla_remota_web` | 148 | Huérfano / desconectado | Pieza interna del servidor HUD. |
| `percepcion_motor` | 15.234 | Huérfano / desconectado | Motor de percepción de alto nivel, alimentado por main. |
| `procesos_herramientas` | 4.579 | Huérfano / desconectado | Registro de procesos para motor_ejecucion. |
| `ui_visual_analizador` | 11.749 | Huérfano / desconectado | Análisis de interfaces para el motor de ejecución. |
| `ui_visual_comparador` | 4.483 | Huérfano / desconectado | Comparación visual de interfaces. |
| `ui_visual_modelo` | 7.081 | Huérfano / desconectado | Modelos de mapa visual de interfaz. |
| `ui_visual_motor` | 9.919 | Huérfano / desconectado | Motor de comprensión de interfaces. |
| `vision_imagen` | 4.282 | Huérfano / desconectado | Motor interno de imágenes; no es acción de voz. |
| `vision_modelo` | 4.469 | Huérfano / desconectado | Modelos internos de comprensión visual. |
| `vision_motor` | 9.724 | Huérfano / desconectado | Motor interno de comprensión visual y OCR. |
| `vision_ocr` | 1.993 | Huérfano / desconectado | Motor interno de OCR. |
| `vision_proveedores` | 5.958 | Huérfano / desconectado | Adaptadores internos de proveedores visuales. |
