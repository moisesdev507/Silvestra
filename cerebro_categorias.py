"""Categorías y palabras clave para la inyección selectiva de acciones en el prompt de Silvestra."""

# Acciones básicas presentes en todos los turnos para consultas generales y recordatorios
ACCIONES_BASE = {
    "poner_recordatorio", "listar_recordatorios", "cancelar_recordatorio",
    "silencio", "buscar", "anotar_pendiente", "cerrar_pendiente",
    "guardar_recuerdo", "olvidar", "consultar_memoria"
}

# Categorías temáticas: (palabras_clave, conjunto_de_acciones)
# Si la palabra clave tiene espacios, se busca como frase en el texto; si es una palabra, coincide palabra exacta.
CATEGORIAS_ACCIONES = {
    "hud": (
        {
            "hud", "jarvis", "reloj", "clima", "cpu", "ram", "orbe", "panel",
            "h u d", "h-u-d", "h.u.d", "jud", "hood", "jut",
            "panel de control", "tablero", "panel de estado"
        },
        {"mostrar_hud", "ocultar_hud", "clima"}
    ),
    "casa": (
        {"casa", "luz", "luces", "bombillo", "bombillos", "ventilador", "abanico", "puerta", "cuarto", "sala", "domotica", "habitacion"},
        {"mostrar_casa", "ocultar_casa", "encender_luz", "apagar_luz", "encender_ventilador", "apagar_ventilador", "abrir_puerta", "cerrar_puerta", "apagar_todo"}
    ),
    "diario": (
        {"diario", "escribe", "entrada", "reflexion", "manana", "matutino"},
        {"leer_diario", "borrar_diario", "escribir_diario", "probar_mensaje_manana"}
    ),
    "musica": (
        {"musica", "cancion", "youtube", "play", "pausar", "reproducir", "tema", "volumen", "pista", "sonar", "canciones", "sonido", "escuchar"},
        {"musica_youtube", "poner_musica", "musica", "pausar_musica", "reanudar_musica", "siguiente_cancion", "anterior_cancion", "subir_volumen", "bajar_volumen", "silenciar", "volumen", "buscar_youtube"}
    ),
    "pantalla": (
        {"pantalla", "mira", "ves", "ver", "leer", "captura", "copiloto", "ventana", "minimizar", "escritorio", "bloquear"},
        {"mirar_pantalla", "captura_pantalla", "guardar_captura", "minimizar_todo", "bloquear_pantalla"}
    ),
    "laptop": (
        {"laptop", "pc", "computadora", "windows", "apagar", "reiniciar", "suspender", "sesion"},
        {"apagar_laptop", "apagar_pc", "apagar_computadora", "reiniciar_laptop", "reiniciar_pc", "suspender_laptop", "suspender_pc", "cerrar_sesion_laptop", "cerrar_sesion"}
    ),
    "aplicaciones": (
        {"abrir", "cerrar", "programa", "app", "aplicacion", "carpeta", "sitio", "web", "navegador", "ir", "google", "gmail", "whatsapp", "calculadora", "bloc", "notas", "explorador"},
        {"abrir_app", "cerrar_app", "ir_a", "abrir_programa", "cerrar_programa", "abrir_carpeta", "abrir_sitio", "abrir_web", "abrir_navegador", "abrir_youtube", "abrir_gmail", "abrir_whatsapp", "abrir_calculadora", "abrir_bloc_de_notas", "abrir_explorador"}
    ),
    "camara": (
        {"camara", "foto", "mirame", "rostro", "cara", "ojo", "gesto", "gestos", "reconocimiento"},
        {"activar_camara", "apagar_camara", "aprender_mi_cara", "enviar_foto_camara"}
    ),
    "estudio": (
        {"estudiar", "estudio", "pomodoro", "examen", "repaso", "temporizador", "nota", "notas", "materia"},
        {"estudiar", "parar_estudio", "examen", "anotar_nota", "leer_notas"}
    ),
    "telegram": (
        {"telegram", "celular", "mensaje", "aviso", "avisar", "telefono", "movil", "nota de voz"},
        {"avisar_celular", "enviar_captura", "enviar_foto_camara", "enviar_nota_voz"}
    ),
    "cuidado": (
        {"salgo", "salida", "voy", "calle", "cuidado", "regreso", "vuelvo", "afuera", "chequeo"},
        {"registrar_salida", "cancelar_salida", "probar_chequeo", "enviar_nota_voz"}
    ),
    "diagnostico": (
        {"proveedor", "proveedores", "modelo", "error", "log", "falla", "diagnostico", "sistema", "silvestra.log"},
        {"estado_proveedores", "explicar_error"}
    ),
    "escenario": (
        {"presentate", "presentacion", "escenario", "presentar", "quien eres", "demo", "pantalla completa"},
        {"presentarse", "cerrar_escenario"}
    ),
    "movimiento": (
        {"pasear", "camina", "caminar", "muevete", "mover", "quieta", "esquina", "centro", "mouse", "raton", "baila", "bailar", "sigueme"},
        {"pasear", "quedarse_quieta", "ir_esquina_derecha", "ir_esquina_izquierda", "ir_centro", "seguir_mouse", "bailar"}
    ),
    "biometria_voz": (
        {"mi voz", "biometria", "calibrar", "registrar voz", "verificacion", "identificar"},
        {"registrar_mi_voz", "calibrar_voz", "activar_verificacion_voz", "desactivar_verificacion_voz"}
    ),
    "atencion": (
        {"atenta", "palabra clave", "despierta", "presencia", "iniciativa", "espontanea", "hablame"},
        {"activar_palabra_clave", "desactivar_palabra_clave", "activar_presencia", "desactivar_presencia", "activar_iniciativa", "desactivar_iniciativa"}
    ),
    "propuestas": (
        {"propuesta", "propuestas", "mejora", "mejorar", "sugerencia", "idea", "aprobar", "rechazar", "pendiente"},
        {"proponer_mejora", "ver_propuestas", "aprobar_propuesta", "rechazar_propuesta", "marcar_hecha", "forzar_propuesta", "probar_propuesta_diaria", "anotar_idea"}
    ),
    "aprendizaje": (
        {"aprendido", "aprendizaje", "perfil", "costumbre", "correccion", "correcciones", "leccion", "reflexionar", "reflexion"},
        {"que_has_aprendido", "olvidar_aprendizaje", "reflexionar_ahora", "reflexionar_aprendizaje", "borrar_perfil", "mis_correcciones", "olvidar_correccion"}
    ),
    "resumen": (
        {"resumir", "resumen", "articulo", "link", "enlace", "portapapeles", "video"},
        {"resumir_pagina", "resumir_video", "resumir_portapapeles"}
    ),
    "tablet": (
        {"tablet", "remota", "servidor tablet", "pantalla remota", "segunda pantalla"},
        {"mostrar_en_tablet", "ocultar_en_tablet", "tablet_modo_normal", "tablet_modo_privado"}
    ),
    "silencio_detener": (
        {"callate", "callar", "para", "parar", "silencio", "detener", "detente", "basta", "shh", "descansa", "duerme"},
        {"callar", "callate", "para", "descansar", "silencio"}
    ),
    "memoria_alias": (
        {"recuerda", "recuerdo", "memoria", "sabes", "olvida"},
        {"recuerda_esto", "que_sabes", "guardar_recuerdo", "olvidar", "consultar_memoria"}
    ),
    "recordatorios_alias": (
        {"recordatorio", "recordar", "acuerdate", "avisame", "aviso", "alarma"},
        {"poner_recordatorio", "listar_recordatorios", "cancelar_recordatorio", "recordar"}
    ),
}
