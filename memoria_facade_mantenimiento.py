"""Métodos auxiliares de mantenimiento para la fachada Memoria."""


class MantenimientoMemoria:
    def actualizar_recuerdo(self, recuerdo_id, nuevo_contenido=None, **campos):
        fila = self.gestor.actualizar(recuerdo_id, self.usuario_id,
                                      nuevo_contenido=nuevo_contenido, **campos)
        self._refrescar_hechos()
        return fila

    def consolidar_recuerdos(self, token_cancelacion=None, progreso=None):
        from memoria_consolidacion import consolidar
        resultado = consolidar(self.almacen, self.usuario_id, token_cancelacion, progreso)
        self._refrescar_hechos()
        return resultado

    def mantenimiento_memoria(self, token_cancelacion=None, progreso=None):
        resultado = self.gestor.mantenimiento(self.usuario_id, token_cancelacion, progreso)
        self._refrescar_hechos()
        return resultado

    def olvidar(self, tema):
        from memoria_olvido import olvidar
        if not tema or not str(tema).strip():
            return "No me dijiste qué recuerdo quieres que olvide."
        total = olvidar(self.almacen, tema, self.usuario_id, explicito=True)
        self._refrescar_hechos()
        return f"Listo. He olvidado {total} recuerdos relacionados." if total else "No encontré recuerdos coincidentes."

    def _refrescar_hechos(self):
        with self._bloqueo:
            self.datos["hechos"] = [r["contenido"] for r in self.almacen.listar_recuerdos(10000, usuario_id=self.usuario_id)]
            self.guardar()
