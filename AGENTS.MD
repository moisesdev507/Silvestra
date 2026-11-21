# Reglas de Arquitectura y Desarrollo — Proyecto Silvestra

## 1. Contexto y Entorno
- **Proyecto:** Silvestra, asistente personal modular en Python 3 sobre Windows 11.
- **Directorio:** `C:\Proyecto_Silvestra`
- **Intérprete obligatorio:** `.venv\Scripts\python.exe` (nunca usar el Python global).
- **Arquitectura vigente (Fase 1 cerrada en commit `202b86c`):**
  - Interfaz desktop flotante en PySide6 (`cara_qt.py`, `eventos.py`, `main.py`).
  - HUD web remoto en tablet Samsung Galaxy Tab A7 vía HTTP/SSE (`pantalla_remota*.py`, `contexto_hud.py`).
  - Percepción y Context Engine en 3 niveles (`detectado`, `probable`, `confirmado`): `contexto_windows.py`, `contexto_motor.py`, `contexto_reglas.py`, `contexto_prompt.py`.
  - Iniciativa contextual cancelable: `iniciativa.py`, `iniciativa_contextual.py`.
  - Planificador jerárquico con grafo anti-ciclos: `planificador_modelo.py`, `planificador.py`.
  - Persistencia atómica thread-safe: `persistencia_segura.py` (`.tmp` + `os.replace` + `RLock`).

## 2. Reglas de Oro (Inquebrantables)
1. **Límite estricto de tamaño en Python:** Ningún archivo `.py` puede superar los **15,360 bytes (15 KB)**. Sin excepciones ni listas blancas. Si crece más, debe dividirse en submódulos cohesivos.
2. **Límite de `TRASPASO.md`:** Nunca debe superar los **6,656 bytes (6.5 KB)**.
3. **Medición real:** Siempre verificar tamaños con `os.path.getsize`, nunca estimaciones.
4. **Cero duplicación:** Antes de crear un módulo o función, inspeccionar y reutilizar los motores existentes.
5. **Seguridad del hilo de PySide6:** Ningún hilo secundario puede tocar widgets ni métodos Qt directamente; toda comunicación hacia la UI pasa por `app.cola`. Prohibido bloquear el hilo principal con red o I/O pesado.
6. **Cero dependencias externas innecesarias:** Priorizar siempre la biblioteca estándar de Python y paquetes ya instalados en `.venv`.
7. **Disciplina de certeza:** Nunca presentar una inferencia (`probable`) como hecho (`detectado` o `confirmado`). Toda inferencia mantiene `permite_accion_automatica: False`.
8. **Seguridad y control humano:** Las tareas largas deben ser supervisables y cancelables. Toda acción sensible, destructiva o con impacto externo requiere permisos y confirmación explícita del usuario.
9. **Git local:** Hacer commits locales limpios solo cuando la etapa esté verificada y aprobada. **Nunca ejecutar `git push`** salvo orden explícita.

## 3. Flujo de Trabajo Obligatorio en Cada Misión
1. **Inspección de solo lectura:** Revisar interfaces reales, contratos y tamaños en bytes antes de tocar código.
2. **Plan Técnico Previo:** Presentar qué archivos se crearán/modificarán y esperar aprobación antes de implementar.
3. **Implementación modular:** Escribir código limpio, tolerante a fallos y protegido con `threading.RLock` cuando comparta estado.
4. **Verificación completa:** Ejecutar pruebas unitarias nuevas + suites existentes + `.venv\Scripts\python.exe prueba_humo.py` (debe salir con código `0` y `0` avisos) + tabla real de `os.path.getsize`.