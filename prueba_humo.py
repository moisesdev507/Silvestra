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
