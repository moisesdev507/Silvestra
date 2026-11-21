"""Coordinador multiusuario de persistencia y memoria de trabajo volátil."""
import threading
import time
from collections import OrderedDict

import memoria_filtro
from memoria_modelos import ElementoTrabajo, Recuerdo, validar_usuario_id


def _cancelado(token):
    return bool(token is not None and callable(getattr(token, "is_set", None)) and token.is_set())


class GestorMemoria:
    def __init__(self, almacen, usuario_id="local", capacidad_trabajo=100, ttl_trabajo=1800):
        self.almacen = almacen
        self.usuario_id = validar_usuario_id(usuario_id)
        self.capacidad_trabajo = max(1, int(capacidad_trabajo))
        self.ttl_trabajo = max(1.0, float(ttl_trabajo))
        self._lock = threading.RLock()
        self._trabajo = {}
        from memoria_grafo import GrafoConocimiento
        self.grafo = GrafoConocimiento(almacen)

    def _uid(self, usuario_id=None):
        return validar_usuario_id(usuario_id if usuario_id is not None else self.usuario_id)

    def guardar(self, contenido, tipo_memoria="semantica", origen="explicito", confianza=0.8,
                categoria="general", metadatos=None, fecha_evento=None, usuario_id=None):
        uid = self._uid(usuario_id)
        if isinstance(contenido, Recuerdo):
            item = contenido
            if item.usuario_id != uid:
                raise PermissionError("El recuerdo pertenece a otro usuario")
        else:
            item = Recuerdo(uid, tipo_memoria, contenido, origen, confianza, categoria,
                            metadatos or {}, fecha_evento)
        if item.tipo_memoria == "trabajo":
            raise ValueError("Memoria de trabajo es volátil; use agregar_trabajo")
        valido, _ = memoria_filtro.es_recuerdo_valido(item.contenido)
        if not valido:
            raise ValueError("El filtro de privacidad o calidad rechazó el recuerdo")
        return self.almacen.guardar_recuerdo(item.contenido, item.tipo_memoria, item.categoria,
            item.origen, item.confianza, item.fecha_evento, item.metadatos,
            usuario_id=uid)

    def buscar(self, consulta, limite=10, tipos=None, usuario_id=None):
        return self.almacen.buscar_texto(consulta, limite, tipos, usuario_id=self._uid(usuario_id))

    def actualizar(self, recuerdo_id, usuario_id=None, **campos):
        uid = self._uid(usuario_id)
        texto = campos.get("nuevo_contenido")
        if texto is not None and not memoria_filtro.es_recuerdo_valido(texto)[0]:
            raise ValueError("El filtro de privacidad o calidad rechazó el recuerdo")
        return self.almacen.actualizar_recuerdo(recuerdo_id, usuario_id=uid, **campos)

    def reemplazar(self, recuerdo_id, nuevo_contenido, usuario_id=None, **campos):
        if not memoria_filtro.es_recuerdo_valido(nuevo_contenido)[0]:
            raise ValueError("El filtro de privacidad o calidad rechazó el recuerdo")
        return self.almacen.reemplazar_recuerdo(recuerdo_id, nuevo_contenido,
            usuario_id=self._uid(usuario_id), **campos)

    def olvidar(self, tema, usuario_id=None):
        return self.almacen.olvidar_por_tema(tema, self._uid(usuario_id))

    def eliminar(self, recuerdo_id, fisico=False, usuario_id=None):
        return self.almacen.eliminar_recuerdo(recuerdo_id, fisico, self._uid(usuario_id))

    def procesar_lote(self, recuerdos, usuario_id=None, token_cancelacion=None):
        uid = self._uid(usuario_id)
        resultados = []
        for item in recuerdos:
            if _cancelado(token_cancelacion):
                return {"resultados": resultados, "cancelado": True}
            try:
                datos = dict(item)
                resultados.append(self.guardar(usuario_id=uid, **datos))
            except (ValueError, PermissionError, TypeError):
                resultados.append(None)
        return {"resultados": resultados, "cancelado": _cancelado(token_cancelacion)}

    def agregar_trabajo(self, clave, contenido, usuario_id=None, ttl=None):
        uid = self._uid(usuario_id)
        if isinstance(contenido, str) and not memoria_filtro.es_recuerdo_valido(contenido)[0]:
            raise ValueError("El filtro de privacidad o calidad rechazó el elemento")
        ahora = time.monotonic()
        item = ElementoTrabajo(uid, clave, contenido, expira_en=ahora + (self.ttl_trabajo if ttl is None else max(1.0, ttl)))
        with self._lock:
            caja = self._trabajo.setdefault(uid, OrderedDict())
            self._purgar(caja, ahora)
            caja[item.clave] = item
            caja.move_to_end(item.clave)
            while len(caja) > self.capacidad_trabajo:
                caja.popitem(last=False)
        return item

    @staticmethod
    def _purgar(caja, ahora):
        for clave in [k for k, v in caja.items() if v.expira_en <= ahora]:
            caja.pop(clave, None)

    def obtener_trabajo(self, clave, usuario_id=None, defecto=None):
        uid = self._uid(usuario_id)
        with self._lock:
            caja = self._trabajo.get(uid, OrderedDict())
            self._purgar(caja, time.monotonic())
            item = caja.get(clave)
            if item:
                caja.move_to_end(clave)
                return item.contenido
            return defecto

    def listar_trabajo(self, usuario_id=None):
        uid = self._uid(usuario_id)
        with self._lock:
            caja = self._trabajo.get(uid, OrderedDict())
            self._purgar(caja, time.monotonic())
            return [ElementoTrabajo(v.usuario_id, v.clave, v.contenido, v.creado_en, v.expira_en)
                    for v in caja.values()]

    def limpiar_memoria_trabajo(self, usuario_id=None):
        uid = self._uid(usuario_id)
        with self._lock:
            return len(self._trabajo.pop(uid, {}))

    def cambiar_perfil(self, nuevo_usuario_id):
        nuevo = validar_usuario_id(nuevo_usuario_id)
        with self._lock:
            previo = self.usuario_id
            self._trabajo.pop(previo, None)
            self.usuario_id = nuevo
        return previo

    def cerrar_perfil(self, usuario_id=None):
        return self.limpiar_memoria_trabajo(usuario_id)

    def mantenimiento(self, usuario_id=None, token_cancelacion=None, progreso=None):
        """Ejecuta consolidación y obsolescencia en grupos cancelables."""
        from memoria_consolidacion import consolidar
        from memoria_olvido import mantener
        uid = self._uid(usuario_id)
        primero = consolidar(self.almacen, uid, token_cancelacion, progreso)
        if primero.get("cancelado"):
            return {"consolidacion": primero, "olvido": {"cancelado": True}}
        segundo = mantener(self.almacen, uid, token_cancelacion, progreso)
        return {"consolidacion": primero, "olvido": segundo}

    def razonar(self, consulta, usuario_id=None, contexto_engine=None, multimodal=None,
                token_cancelacion=None, limite=8):
        from memoria_razonamiento import razonar
        return razonar(self, consulta, self._uid(usuario_id), contexto_engine,
                       multimodal, token_cancelacion, limite)
