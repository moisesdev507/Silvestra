"""Modelos validados para los cuatro tipos de memoria."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import re


class TipoMemoria(str, Enum):
    EPISODICA = "episodica"
    SEMANTICA = "semantica"
    TRABAJO = "trabajo"
    PROCEDIMENTAL = "procedimental"


class OrigenMemoria(str, Enum):
    EXPLICITO = "explicito"
    INFERIDO = "inferido"
    MULTIMODAL = "multimodal"
    MIGRADO = "migrado"
    SISTEMA = "sistema"


def validar_usuario_id(usuario_id):
    valor = str(usuario_id or "")
    if valor != valor.strip() or not re.fullmatch(r"[\w.@:-]{1,128}", valor, re.UNICODE):
        raise ValueError("usuario_id inválido")
    return valor


def limpiar_nombre(texto):
    if not texto:
        return texto
    texto = str(texto).strip()
    texto = re.sub(r"^(hola[,.! ]*)?(me llamo|mi nombre es|yo soy|soy|te llamas|te llamarás|"
                   r"tu nombre es|llámame|puedes llamarme)\s+", "", texto, flags=re.I)
    return texto.strip(" .,!¡¿?")


def _valor_enum(valor, clase):
    try:
        return clase(valor).value
    except (ValueError, TypeError):
        raise ValueError(f"{clase.__name__} inválido") from None


def _marca(valor=None):
    if valor is None:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not isinstance(valor, str):
        raise ValueError("marca temporal inválida")
    try:
        datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("marca temporal inválida") from None
    return valor


@dataclass
class Recuerdo:
    usuario_id: str
    tipo_memoria: str
    contenido: str
    origen: str = "explicito"
    confianza: float = 0.8
    categoria: str = "general"
    metadatos: dict = field(default_factory=dict)
    fecha_evento: str | None = None
    creado_en: str = field(default_factory=_marca)
    actualizado_en: str = field(default_factory=_marca)

    def __post_init__(self):
        self.usuario_id = validar_usuario_id(self.usuario_id)
        self.tipo_memoria = _valor_enum(self.tipo_memoria, TipoMemoria)
        self.origen = _valor_enum(self.origen, OrigenMemoria)
        if not isinstance(self.contenido, str) or not self.contenido.strip():
            raise ValueError("contenido inválido")
        self.contenido = self.contenido.strip()
        try:
            self.confianza = float(self.confianza)
        except (ValueError, TypeError):
            raise ValueError("confianza inválida") from None
        if not 0 <= self.confianza <= 1:
            raise ValueError("confianza fuera de rango")
        if not isinstance(self.metadatos, dict):
            raise ValueError("metadatos deben ser un objeto")
        try:
            json.dumps(self.metadatos, ensure_ascii=False)
        except (TypeError, ValueError):
            raise ValueError("metadatos deben ser JSON serializable") from None
        self.creado_en = _marca(self.creado_en)
        self.actualizado_en = _marca(self.actualizado_en)
        if self.fecha_evento is not None:
            self.fecha_evento = _marca(self.fecha_evento)


@dataclass
class ElementoTrabajo:
    usuario_id: str
    clave: str
    contenido: object
    creado_en: str = field(default_factory=_marca)
    expira_en: float = 0.0

    def __post_init__(self):
        self.usuario_id = validar_usuario_id(self.usuario_id)
        if not isinstance(self.clave, str) or not self.clave.strip():
            raise ValueError("clave de trabajo inválida")
        self.clave = self.clave.strip()
