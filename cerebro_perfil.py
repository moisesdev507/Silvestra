"""Perfilado liviano de latencias pre-LLM y carril ultrarrápido de conversación."""
import re
import time
import unicodedata

# Patrones de frases breves conversacionales que no requieren RAG ni I/O pesado
_FRASES_ULTRARRAPIDAS = {
    "ok", "gracias", "ok gracias", "muchas gracias", "muchas gracias lyris",
    "vale", "entendido", "de acuerdo", "perfecto", "listo", "dale",
    "hola", "hola lyris", "buenas", "buenos dias", "buenas tardes", "buenas noches",
    "adios", "chao", "hasta luego", "nos vemos", "bye", "bien", "muy bien",
    "genial", "excelente", "comprendido", "claro", "si", "no"
}

_PALABRAS_PESADAS = {
    "recuerda", "recuerdas", "guarda", "anota", "que tengo", "que sabes",
    "calendario", "agenda", "correo", "gmail", "drive", "evento",
    "abre", "abrir", "cierra", "cerrar", "busca", "buscar", "calcula",
    "resuelve", "codigo", "error", "ayuda", "explica", "porque"
}


def normalizar_texto(texto):
    """Limpia tildes, signos de puntuación y espacios extras."""
    if not texto:
        return ""
    txt = unicodedata.normalize("NFKD", str(texto).strip().lower())
    sin_tildes = "".join(c for c in txt if not unicodedata.combining(c))
    limpio = re.sub(r"[^\w\s]", " ", sin_tildes)
    return " ".join(limpio.split())


def es_frase_ultrarrapida(texto):
    """Detecta si la frase es un saludo breve, agradecimiento o acuse simple."""
    t = normalizar_texto(texto)
    if not t:
        return False
    if t in _FRASES_ULTRARRAPIDAS:
        return True
    palabras = t.split()
    if len(palabras) <= 3 and len(t) <= 22:
        if any(p in _PALABRAS_PESADAS for p in palabras):
            return False
        # Si consiste exclusivamente en componentes de cortesía
        cortesia = {"hola", "buenas", "dias", "tardes", "noches", "lyris", "silvestra", "ok", "gracias", "vale", "chao", "adios"}
        if all(p in cortesia for p in palabras):
            return True
    return False


class PerfilTurno:
    """Cronómetro liviano para desglosar tramos de tiempo antes del primer token."""

    def __init__(self, texto=""):
        self.texto = texto
        self.t_inicio = time.perf_counter()
        self.t_pre_enrutado = 0.0
        self.t_memoria = 0.0
        self.t_despacho_llm = 0.0
        self._reportado = False

    def marcar_pre_enrutado(self):
        if not self.t_pre_enrutado:
            self.t_pre_enrutado = time.perf_counter()

    def marcar_memoria(self):
        if not self.t_memoria:
            self.t_memoria = time.perf_counter()

    def marcar_despacho_llm(self):
        if not self.t_despacho_llm:
            self.t_despacho_llm = time.perf_counter()

    def emitir_primer_token(self):
        """Imprime la métrica resumida exactamente una vez al llegar el primer token."""
        if self._reportado:
            return
        self._reportado = True
        t_ahora = time.perf_counter()
        t_pre = (self.t_pre_enrutado - self.t_inicio) * 1000.0 if self.t_pre_enrutado else 0.0
        ref_mem = self.t_pre_enrutado or self.t_inicio
        t_mem = (self.t_memoria - ref_mem) * 1000.0 if self.t_memoria else 0.0
        ref_llm = self.t_despacho_llm or self.t_memoria or ref_mem
        t_llm = (t_ahora - ref_llm) * 1000.0
        print(f"[perfil] pre_enrutado={t_pre:.1f}ms memoria={t_mem:.1f}ms despacho_llm={t_llm:.1f}ms", flush=True)


# Instancia activa por turno actual
_perfil_actual = None


def iniciar_perfil(texto=""):
    global _perfil_actual
    _perfil_actual = PerfilTurno(texto)
    return _perfil_actual


def obtener_perfil():
    return _perfil_actual


def inicializar_metricas_turno(app, texto):
    """Configura las métricas del turno según si el origen es voz o texto/chat."""
    origen = getattr(app, "origen_entrada_actual", "chat")
    if origen == "microfono":
        t_habla = getattr(getattr(app, "oido", None), "t_fin_habla", getattr(getattr(app, "oido", None), "t_fin_escucha", time.time()))
        t_txt = getattr(getattr(app, "oido", None), "t_texto", time.time())
        app.t_fin_habla = t_habla
        app.t_inicio_texto = None
    else:
        t_ahora = time.time()
        t_habla = None
        t_txt = t_ahora
        app.t_fin_habla = None
        app.t_inicio_texto = t_ahora
    app.metricas_turno = {"t_fin_habla": t_habla, "t_texto": t_txt, "t_primer_token": None}
    iniciar_perfil(texto)


def notificar_primer_token(app):
    """Registra t_primer_token y emite la métrica de perfilado si aplica."""
    if hasattr(app, "metricas_turno") and isinstance(app.metricas_turno, dict):
        if app.metricas_turno.get("t_primer_token") is None:
            app.metricas_turno["t_primer_token"] = time.time()
    p = obtener_perfil()
    if p:
        p.emitir_primer_token()
