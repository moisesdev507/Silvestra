"""Formación, promoción y evaluación de aprendizajes a partir de evidencia."""
import hashlib
import json
import threading
from experiencia_almacen import AlmacenExperiencias
from experiencia_analizador import analizar
from experiencia_modelos import Aprendizaje, Experiencia


def _cancelado(token):
    return bool(token is not None and callable(getattr(token, "is_set", None)) and token.is_set())


class MotorExperiencias:
    def __init__(self, almacen, usuario_id=None):
        self.repo = AlmacenExperiencias(almacen)
        self.usuario_id = self.repo.uid(usuario_id)
        self._lock = threading.RLock()

    def registrar(self, datos, token_cancelacion=None):
        if _cancelado(token_cancelacion):
            return {"cancelado": True, "aprendizaje": None}
        d = dict(datos or {})
        d["usuario_id"] = self.usuario_id
        exp = Experiencia(**{k:v for k,v in d.items() if k in Experiencia.__dataclass_fields__})
        limpio = analizar(exp.a_dict())
        if not limpio.get("util"):
            return {"registrada": False, "motivo": limpio.get("motivo")}
        dato = exp.a_dict(); dato["clave_patron"] = limpio["clave_patron"]
        with self._lock:
            self.repo.guardar_experiencia(dato, limpio["clave_patron"], self.usuario_id)
            filas = self.repo.experiencias(limpio["clave_patron"], self.usuario_id)
            # Solo fuentes independientes cuentan para promover un patrón.
            validas, fuentes = [], set()
            for x in filas:
                origen = tuple(x.get("origen_ids") or ())
                if not x.get("verificada") or x.get("exito") is None or not origen or origen in fuentes:
                    continue
                fuentes.add(origen); validas.append(x)
            apoyos = sum(bool(x["exito"]) == bool(limpio["exito"]) for x in validas)
            contras = len(validas) - apoyos
            conf = (1 + apoyos) / (2 + apoyos + contras)
            tipo = "patron" if len(validas) >= 3 else ("exito" if limpio["exito"] is True else "error_evitar")
            estado = "validado" if tipo == "patron" and apoyos >= 3 and apoyos > contras else "preliminar"
            if contras >= apoyos and contras:
                estado = "contradicho"
            ident = "apr_" + hashlib.sha256(limpio["clave_patron"].encode()).hexdigest()[:20]
            interp = limpio["interpretacion"]
            if limpio["exito"] is False:
                interp += " Estrategia preventiva: revisar factores antes de reintentar."
            a = Aprendizaje(ident, self.usuario_id, tipo,
                tuple(y for x in validas for y in x.get("origen_ids", ())),
                limpio["observado"], interp, conf, limpio["condiciones"],
                ("No generalizar fuera de condiciones comparables.",), estado, limpio["clave_patron"])
            self.repo.guardar_aprendizaje(a.a_dict(), self.usuario_id)
            return {"registrada": True, "aprendizaje": a.a_dict(), "evidencias": len(validas)}

    def registrar_informe(self, informe, token_cancelacion=None):
        d = informe.a_dict() if callable(getattr(informe, "a_dict", None)) else dict(informe or {})
        solicitud = d.get("solicitud_original", {})
        evidencia = d.get("evidencia") or {}
        verificada = d.get("estado_final") in {"verificado", "recuperado"} or bool(evidencia.get("verificada"))
        exito = True if verificada else False if d.get("estado_final") == "fallido" else None
        return self.registrar({"resultado_esperado": d.get("resultado_esperado"),
            "resultado_observado": json.dumps(evidencia, ensure_ascii=False, default=str),
            "factores": d.get("errores_detectados", ()), "origen_ids": [d.get("id_solicitud"), solicitud.get("id_plan"), solicitud.get("id_tarea")],
            "verificada": verificada, "exito": exito, "categoria": solicitud.get("herramienta", "verificacion"),
            "condiciones": ["resultado de verificación"]}, token_cancelacion)

    def registrar_ejecucion(self, solicitud, resultado, esperado=None):
        s = solicitud.a_dict() if callable(getattr(solicitud, "a_dict", None)) else dict(solicitud or {})
        r = resultado.a_dict() if callable(getattr(resultado, "a_dict", None)) else dict(resultado or {})
        # Una salida sin informe verificador nunca se trata como éxito confirmado.
        return self.registrar({"resultado_esperado": str(esperado or ""),
            "resultado_observado": json.dumps({"estado":r.get("estado"),"exito":r.get("exito"),"error":r.get("error")},ensure_ascii=False),
            "factores": [r.get("herramienta", "")], "origen_ids": [s.get("id_solicitud"),s.get("id_plan"),s.get("id_tarea")],
            "verificada": False, "exito": None, "categoria": r.get("herramienta", "ejecucion")})

    def recuperar(self, consulta, limite=5):
        import re
        tokens = set(re.findall(r"[a-záéíóúñ]{3,}", str(consulta or "").casefold()))
        filas = self.repo.listar_aprendizajes(self.usuario_id)
        scored = []
        for x in filas:
            if x["estado"] not in {"preliminar", "validado"}:
                continue
            words = set(re.findall(r"[a-záéíóúñ]{3,}", (x.get("clave_patron", "").replace("_", " ") + " " + x.get("interpretacion", "")).casefold()))
            score = len(tokens & words) / max(1,len(tokens | words))
            if score >= .05:
                scored.append((score,x))
        return [x for _,x in sorted(scored,key=lambda z:(z[0],z[1]["confianza"]),reverse=True)[:max(0,min(int(limite),20))]]

    def evaluar_eficacia(self, id_aprendizaje, antes, despues):
        mejora = self.repo.evaluar(id_aprendizaje, antes, despues, self.usuario_id)
        filas = [x for x in self.repo.listar_aprendizajes(self.usuario_id, estados=("preliminar","validado","contradicho")) if x["id_aprendizaje"]==id_aprendizaje]
        if filas and not mejora:
            x=filas[0]; x["confianza"]=max(0.,x["confianza"]-.2); x["estado"]="obsoleto" if x["confianza"]<.25 else "contradicho"
            self.repo.guardar_aprendizaje(x,self.usuario_id)
        return mejora

    def revisar(self, id_aprendizaje, estado, interpretacion=None):
        if estado not in {"validado","contradicho","obsoleto","descartado","preliminar"}:
            raise ValueError("estado inválido")
        for x in self.repo.listar_aprendizajes(self.usuario_id, estados=tuple(__import__('experiencia_modelos').ESTADOS)):
            if x["id_aprendizaje"]==id_aprendizaje:
                x["estado"]=estado
                if interpretacion is not None: x["interpretacion"]=str(interpretacion)[:1200]
                self.repo.guardar_aprendizaje(x,self.usuario_id); return True
        return False
