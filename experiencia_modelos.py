"""Contratos validados para experiencias y aprendizajes trazables."""
from dataclasses import asdict, dataclass, field
import uuid

ESTADOS = {"preliminar", "validado", "contradicho", "obsoleto", "descartado"}
TIPOS = {"exito", "error_evitar", "patron", "estrategia"}


def _textos(valores):
    if isinstance(valores, str):
        valores = (valores,)
    return tuple(str(x).strip()[:240] for x in (valores or ()) if x is not None and str(x).strip())


@dataclass
class Experiencia:
    usuario_id: str
    resultado_esperado: str = ""
    resultado_observado: str = ""
    factores: tuple = ()
    origen_ids: tuple = ()
    verificada: bool = False
    exito: bool | None = None
    condiciones: tuple = ()
    categoria: str = "general"
    id_experiencia: str = field(default_factory=lambda: "exp_" + uuid.uuid4().hex)

    def __post_init__(self):
        self.usuario_id = str(self.usuario_id or "local")
        self.resultado_esperado = str(self.resultado_esperado or "").strip()[:1200]
        self.resultado_observado = str(self.resultado_observado or "").strip()[:1200]
        self.factores, self.origen_ids = _textos(self.factores), _textos(self.origen_ids)
        self.condiciones = _textos(self.condiciones)
        self.categoria = str(self.categoria or "general").strip().casefold()[:100]
        if not self.usuario_id or not self.resultado_observado:
            raise ValueError("experiencia incompleta")
        if self.exito is not None and not isinstance(self.exito, bool):
            raise TypeError("exito debe ser booleano o None")

    def a_dict(self):
        return asdict(self)


@dataclass
class Aprendizaje:
    id_aprendizaje: str
    usuario_id: str
    tipo: str
    origen_ids: tuple
    resultado_observado: str
    interpretacion: str
    confianza: float
    condiciones_aplicabilidad: tuple = ()
    limitaciones: tuple = ()
    estado: str = "preliminar"
    clave_patron: str = "general"

    def __post_init__(self):
        if self.tipo not in TIPOS or self.estado not in ESTADOS:
            raise ValueError("tipo o estado de aprendizaje inválido")
        self.confianza = float(self.confianza)
        if not 0 <= self.confianza <= 1:
            raise ValueError("confianza fuera de [0,1]")
        self.origen_ids = _textos(self.origen_ids)
        self.condiciones_aplicabilidad = _textos(self.condiciones_aplicabilidad)
        self.limitaciones = _textos(self.limitaciones)
        self.resultado_observado = str(self.resultado_observado or "")[:1200]
        self.interpretacion = str(self.interpretacion or "")[:1200]

    def a_dict(self):
        return asdict(self)
