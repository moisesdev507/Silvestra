"""Prueba de humo (smoke test) rápida para verificar la integridad del sistema Silvestra."""
import os
import sys
import glob
import py_compile

def verificar_compilacion_y_tamanos():
    archivos_py = glob.glob("*.py")
    if not archivos_py:
        print("ERROR: No se encontraron archivos .py en la raíz.")
        return False
    
    excesivos = []
    errores_sintaxis = []
    
    LEGACY_CONOCIDOS = {"resumen.py", "telegram_medios.py", "cara.py"}
    for ruta in archivos_py:
        tam = os.path.getsize(ruta)
        nombre = os.path.basename(ruta)
        if tam > 15360 and nombre not in LEGACY_CONOCIDOS:
            excesivos.append((ruta, tam))
        elif tam > 15360:
            print(f"AVISO: Archivo legacy conocido > 15 KB: {nombre} ({tam/1024:.2f} KB)")
        try:
            py_compile.compile(ruta, doraise=True)
        except Exception as e:
            errores_sintaxis.append((ruta, str(e)))
            
    if excesivos:
        print("ERROR: Archivos que superan el límite de 15 KB (15,360 bytes):")
        for ruta, tam in excesivos:
            print(f"  - {ruta}: {tam} bytes ({tam/1024:.2f} KB)")
        return False
        
    if errores_sintaxis:
        print("ERROR: Errores de sintaxis detectados:")
        for ruta, err in errores_sintaxis:
            print(f"  - {ruta}: {err}")
        return False
        
    print(f"OK: {len(archivos_py)} archivos .py verificados (sintaxis y <= 15 KB).")
    return True

def verificar_modulos_clave():
    try:
        import config
        import sesion_http
        import voz_cache
        import calidad_respuesta
        import acciones
        import conversacion
        import oido
        import voz
        print("OK: Módulos clave importados correctamente.")
    except Exception as e:
        print(f"ERROR al importar módulos clave: {e}")
        return False

    # Verificar calidad lingüística
    valido, mot = calidad_respuesta.analizar_calidad_texto("Hola, ¿cómo estás hoy?")
    assert valido, f"Falso positivo en frase válida: {mot}"
    
    valido, mot = calidad_respuesta.analizar_calidad_texto("Estoy bien, gracias, ¿y tú?")
    assert valido, f"Falso positivo en 'Estoy bien': {mot}"
    
    valido, mot = calidad_respuesta.analizar_calidad_texto("Esto nunca se impun darte qué el proveres")
    assert not valido, "Fallo al detectar palabras corruptas"
    print("OK: Filtro de calidad lingüística verificado.")

    # Verificar caché de voz y muletillas de espera
    sonido = voz_cache.obtener_siguiente_muletilla()
    assert sonido in voz_cache.SONIDOS_ESPERA, f"Sonido de espera inválido: {sonido}"
    voz_cache.guardar_audio_cache("hola", b"wav_fake")
    assert voz_cache.obtener_audio_cache("hola") == b"wav_fake", "Fallo en caché de audio"
    print("OK: Caché de voz y muletillas verificados.")

    # Verificar sesión HTTP compartida
    ses = sesion_http.obtener_sesion()
    assert ses is not None, "Sesión HTTP nula"
    print("OK: Sesión HTTP persistente verificada.")
    
    # Verificar acciones
    acciones.registrar("test_humo", lambda: "ok", "Acción de prueba de humo")
    ok, msg = acciones.ejecutar("test_humo")
    assert ok, f"Fallo al ejecutar acción registrada: {msg}"
    print("OK: Registro y ejecución de acciones verificado.")

    # Verificar control_seguridad y control_laptop
    import queue
    import control_seguridad
    import control_laptop

    # 1. Extracción de dígitos de voz y texto
    assert control_seguridad.extraer_codigo("dos cero cero seis") == "2006"
    assert control_seguridad.extraer_codigo("2006") == "2006"
    assert control_seguridad.extraer_codigo("cero cero cero cero") == "0000"
    print("OK: Extracción de código por voz/dígitos verificada.")

    # 2. Detección de acciones prohibidas
    assert control_seguridad.es_accion_prohibida("borrar archivos del sistema")
    assert control_seguridad.es_accion_prohibida("modificar config.py")
    assert control_seguridad.es_accion_prohibida("pip install malware")
    assert not control_seguridad.es_accion_prohibida("abrir calculadora")
    print("OK: Filtro de acciones prohibidas verificado.")

    # 3. Flujo interactivo con simulación de app
    class DummyApp:
        def __init__(self):
            self.cola = queue.Queue()
            self.origen_entrada_actual = "chat"
            self.frases = []
        def decir(self, txt, ms=2000):
            self.frases.append(txt)

    app_dummy = DummyApp()
    control_laptop.instalar(app_dummy)
    cs = app_dummy.control_seguridad
    cs.modo_simulacion = True
    cs.limpiar_pendiente()
    cs.bloqueado_hasta = 0.0

    # Solicitar apagar laptop (sin código no se apaga, pide el código)
    ok, msg = acciones.ejecutar("apagar_laptop")
    assert ok, f"Fallo al invocar apagar_laptop: {msg}"
    assert cs.tiene_pendiente(), "Debe quedar en espera de código"
    assert any("Dime el código" in f for f in app_dummy.frases), "Debe pedir 'Dime el código'"

    # 3 intentos fallidos consecutivos deben bloquear
    cs.verificar_codigo("codigo 1111")
    assert cs.tiene_pendiente(), "Intento 1 fallido debe mantener espera"
    assert cs.intentos_fallidos == 1

    cs.verificar_codigo("codigo 2222")
    assert cs.tiene_pendiente(), "Intento 2 fallido debe mantener espera"
    assert cs.intentos_fallidos == 2

    cs.verificar_codigo("codigo 3333")
    assert not cs.tiene_pendiente(), "Intento 3 fallido debe limpiar pendiente"
    assert cs.bloqueado_hasta > 0, "Debe quedar bloqueado temporalmente tras 3 intentos"
    print("OK: Desafío de seguridad sin código y bloqueo a 3 intentos fallidos verificado.")

    # 4. Verificación de éxito en simulación (con código correcto)
    cs.bloqueado_hasta = 0.0
    acciones.ejecutar("apagar_laptop")
    assert cs.tiene_pendiente()
    codigo_esperado = str(getattr(config, "CODIGO_SEGURIDAD", "0000")).strip()
    resuelto = cs.verificar_codigo(codigo_esperado)
    assert resuelto, "Debe aceptar el código correcto"
    assert not cs.tiene_pendiente(), "Pendiente debe quedar resuelto tras éxito"

    # Verificar que el código NUNCA fue escrito a acciones_log.txt
    if os.path.exists(control_seguridad.LOG_FILE):
        with open(control_seguridad.LOG_FILE, "r", encoding="utf-8") as f:
            contenido_log = f.read()
        if len(codigo_esperado) >= 3 and codigo_esperado != "0000":
            assert codigo_esperado not in contenido_log, "ALERTA: El código de seguridad apareció en acciones_log.txt"
    print("OK: Control de seguridad y control_laptop verificados exitosamente.")

    return True

def main():
    print("=== INICIANDO PRUEBA DE HUMO DE SILVESTRA ===")
    paso1 = verificar_compilacion_y_tamanos()
    if not paso1:
        sys.exit(1)
        
    paso2 = verificar_modulos_clave()
    if not paso2:
        sys.exit(1)
        
    print("=== [PRUEBA_HUMO] TODOS LOS TESTS PASARON EXITOSAMENTE ===")
    sys.exit(0)

if __name__ == "__main__":
    main()
