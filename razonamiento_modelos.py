"""Contratos inmutables y serializables del razonamiento inteligente."""
from dataclasses import asdict, dataclass

COMPLEJIDADES = {"simple", "compuesto", "diagnostico", "comparativo", "planificacion_preliminar"}
PROCEDENCIAS = {"vivo_confirmado", "vivo_probable", "multimodal", "memoria_explicita", "memoria_inferida", "grafo"}


def _confianza(valor):
    if valor is None:
        return None
    numero = float(valor)
    if not 0.0 <= numero <= 1.0:
        raise ValueError("confianza fuera de [0,1]")
    return numero


@dataclass(frozen=True, slots=True)
class ProblemaEstructurado:
    consulta: str
    objetivo: str
    complejidad: str
    restricciones: tuple[str, ...] = ()

    def __post_init__(self):
        if self.complejidad not in COMPLEJIDADES:
            raise ValueError("complejidad no válida")


@dataclass(frozen=True, slots=True)
class Subproblema:
    id: str
    orden: int
    descripcion: str
    premisas: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenciaReferenciada:
    id: str | int | None
    contenido: str
    procedencia: str
    confianza: float | None
    clase: str
    actual: bool = False

    def __post_init__(self):
        if self.procedencia not in PROCEDENCIAS:
            raise ValueError("procedencia no válida")
        if self.clase not in {"hecho", "inferencia", "hipotesis"}:
            raise ValueError("clase epistémica no válida")
        object.__setattr__(self, "confianza", _confianza(self.confianza))
        object.__setattr__(self, "contenido", str(self.contenido or "")[:500])


@dataclass(frozen=True, slots=True)
class HipotesisEvaluada:
    id: str
    texto: str
    tipo: str
    evidencia_favor: tuple[str, ...] = ()
    evidencia_contra: tuple[str, ...] = ()
    contradicciones: tuple[str, ...] = ()
    riesgos: tuple[str, ...] = ()
    confianza: float | None = None
    descartada: bool = False

    def __post_init__(self):
        if self.tipo not in {"hipotesis", "alternativa"}:
            raise ValueError("tipo de evaluación no válida")
        object.__setattr__(self, "confianza", _confianza(self.confianza))


@dataclass(frozen=True, slots=True)
class ConclusionJustificada:
    texto: str
    premisas: tuple[str, ...] = ()
    evidencias: tuple[str, ...] = ()
    relaciones: tuple[str, ...] = ()
    alternativas_descartadas: tuple[str, ...] = ()
    confianza: float | None = None

    def __post_init__(self):
        object.__setattr__(self, "confianza", _confianza(self.confianza))


@dataclass(frozen=True, slots=True)
class ResultadoRazonamientoInteligente:
    problema: ProblemaEstructurado
    subproblemas: tuple[Subproblema, ...] = ()
    hechos: tuple[EvidenciaReferenciada, ...] = ()
    contexto_vivo: tuple[EvidenciaReferenciada, ...] = ()
    inferencias: tuple[EvidenciaReferenciada, ...] = ()
    hipotesis: tuple[HipotesisEvaluada, ...] = ()
    alternativas: tuple[HipotesisEvaluada, ...] = ()
    conclusiones: tuple[ConclusionJustificada, ...] = ()
    contradicciones: tuple[tuple[str, ...], ...] = ()
    informacion_faltante: tuple[str, ...] = ()
    confianza_global: float | None = None
    incertidumbre: tuple[str, ...] = ()
    errores: tuple[str, ...] = ()
    cancelado: bool = False

    def __post_init__(self):
        object.__setattr__(self, "confianza_global", _confianza(self.confianza_global))

    def a_dict(self):
        return asdict(self)
