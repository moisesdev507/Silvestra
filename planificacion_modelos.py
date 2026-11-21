"""Modelos serializables para estrategia, riesgo, decisión y progreso."""
from dataclasses import asdict, dataclass, field

ESTADOS_DECISION = {"recomendacion", "aprobacion_usuario", "autorizacion_ejecucion"}
ESTADOS_APROBACION = {"no_requerida", "pendiente", "aprobada", "rechazada"}
ESTADOS_AUTORIZACION = {"no_solicitada", "pendiente", "autorizada", "denegada"}


def confianza(valor):
    if valor is None:
        return None
    n = float(valor)
    if not 0 <= n <= 1:
        raise ValueError("confianza fuera de [0,1]")
    return n


@dataclass(frozen=True, slots=True)
class ObjetivoPlan:
    principal: str
    secundarios: tuple[str, ...] = ()
    requisitos: tuple[str, ...] = ()
    restricciones: tuple[str, ...] = ()
    informacion_faltante: tuple[str, ...] = ()
    recursos_disponibles: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CriterioExito:
    id_tarea: str
    descripcion: str
    evidencia_requerida: str
    requiere_confirmacion_usuario: bool = True


@dataclass(frozen=True, slots=True)
class AlternativaEvaluada:
    id: str
    titulo: str
    ventajas: tuple[str, ...] = ()
    desventajas: tuple[str, ...] = ()
    costo: float | None = None
    complejidad: float = 0.5
    riesgo: float = 0.5
    puntaje: float | None = None
    justificacion: str = ""
    evidencia: tuple[str, ...] = ()

    def __post_init__(self):
        for key in ("complejidad", "riesgo"):
            n = float(getattr(self, key))
            if not 0 <= n <= 1:
                raise ValueError(f"{key} fuera de [0,1]")
            object.__setattr__(self, key, n)
        object.__setattr__(self, "puntaje", confianza(self.puntaje))
        if self.costo is not None and float(self.costo) < 0:
            raise ValueError("costo no puede ser negativo")


@dataclass(frozen=True, slots=True)
class RiesgoPlan:
    id: str
    descripcion: str
    probabilidad: float | None
    impacto: str
    medida_preventiva: str
    procedencia: str = "analisis"

    def __post_init__(self):
        object.__setattr__(self, "probabilidad", confianza(self.probabilidad))


@dataclass(frozen=True, slots=True)
class DecisionPlan:
    alternativa_id: str | None
    justificacion: str
    recomendacion: bool = True
    aprobacion_usuario: str = "pendiente"
    autorizacion_ejecucion: str = "no_solicitada"
    evidencia: tuple[str, ...] = ()
    confianza: float | None = None

    def __post_init__(self):
        if self.aprobacion_usuario not in ESTADOS_APROBACION:
            raise ValueError("estado de aprobación inválido")
        if self.autorizacion_ejecucion not in ESTADOS_AUTORIZACION:
            raise ValueError("estado de autorización inválido")
        if self.autorizacion_ejecucion == "autorizada" and self.aprobacion_usuario != "aprobada":
            raise ValueError("la autorización de ejecución requiere aprobación del usuario")
        if self.aprobacion_usuario == "aprobada" and not self.recomendacion:
            raise ValueError("no se puede aprobar una recomendación inexistente")
        object.__setattr__(self, "confianza", confianza(self.confianza))


@dataclass(frozen=True, slots=True)
class AnalisisPlan:
    objetivo: ObjetivoPlan
    criterios_exito: tuple[CriterioExito, ...] = ()
    alternativas: tuple[AlternativaEvaluada, ...] = ()
    riesgos: tuple[RiesgoPlan, ...] = ()
    decision: DecisionPlan = field(default_factory=lambda: DecisionPlan(None, "Pendiente de información"))
    contexto_probable: tuple[str, ...] = ()
    contexto_confirmado: tuple[str, ...] = ()
    contexto_huella: str = ""
    cancelado: bool = False

    def a_dict(self):
        return asdict(self)

    @classmethod
    def de_dict(cls, data):
        data = dict(data or {})
        return cls(ObjetivoPlan(**data.get("objetivo", {})),
            tuple(CriterioExito(**x) for x in data.get("criterios_exito", ())),
            tuple(AlternativaEvaluada(**x) for x in data.get("alternativas", ())),
            tuple(RiesgoPlan(**x) for x in data.get("riesgos", ())),
            DecisionPlan(**data.get("decision", {"alternativa_id": None, "justificacion": ""})),
            tuple(data.get("contexto_probable", ())), tuple(data.get("contexto_confirmado", ())),
            str(data.get("contexto_huella", "")),
            bool(data.get("cancelado", False)))
