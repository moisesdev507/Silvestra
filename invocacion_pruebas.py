"""Doble mínimo de aplicación para los tests de invocación natural."""
import queue
import threading
from types import SimpleNamespace

import conversacion
import invocacion_lyris


class CaraFalsa:
    def __init__(self):
        self.escuchando = False
        self.hablando = False

    def poner_escuchando(self, valor):
        self.escuchando = bool(valor)

    def poner_hablando(self, valor):
        self.hablando = bool(valor)

    def decir(self, texto, *_a, **_k):
        self.hablando = True
        self.ultimo_burbuja = texto

    def asentir(self, *_a):
        pass

    def fijar_emocion(self, *_a):
        pass

    def programar_retorno_neutral(self, *_a):
        pass


def fabricar_app():
    """Devuelve (app, enviados, hablado) sin hilos ni micrófono reales."""
    enviados, hablado = [], []

    class OidoFalso:
        bloqueo = threading.RLock()
        ultimo_audio = None
        duracion_ultimo_audio = 0.0

        def escuchar(self, **_kw):
            return None

    app = SimpleNamespace(
        cola=queue.Queue(),
        cara=CaraFalsa(),
        memoria=SimpleNamespace(nombre="Lyris", creador="Usuario"),
        voz=SimpleNamespace(ocupada=lambda: False),
        oido=OidoFalso(),
        conversacion=False,
        escuchando=False,
        descansando=False,
        musica_activa=False,
        silencios=0,
        flujo=None,
        pendiente_descanso=False,
        _generacion_escucha=0,
        _t_accion_llm=0,
        _flujo_cerrado=False,
        _iniciar_reflexion=lambda: None,
        _es_eco=lambda _t: False,
    )
    app._dejar_de_escuchar = lambda: conversacion.dejar_de_escuchar(app)
    app.escuchar = lambda: conversacion.escuchar(app)
    app.descansar = lambda: None
    app.decir = lambda texto, **_kw: (hablado.append(texto), app.cara.decir(texto))

    def enviar(texto):
        enviados.append(texto)
        app.cara.decir(f"Respuesta: {texto}")
        app.cola.put(("fin_voz", None))

    app.enviar = enviar
    app.invocacion = invocacion_lyris.GestorInvocacion(app)
    app.invocacion.vivo = True  # bucle interior, sin hilo de micrófono real
    app.invocacion_ambiental = True
    return app, enviados, hablado
