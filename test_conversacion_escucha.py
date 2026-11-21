"""Regresiones de escucha al alternar conversación y cancelar locuciones."""
import queue
import threading
import time
import unittest
import datetime
from types import SimpleNamespace
from unittest.mock import patch

from conversacion import alternar_conversacion
from voz import Flujo, Voz
from oido import Oido
from calidad_respuesta import analizar_calidad_texto
import casa
import conversacion
import eventos
from cerebro import Cerebro
from memoria_filtro import es_recuerdo_valido


class TestReanudacionEscucha(unittest.TestCase):
    def test_descansa_palabra_clave_restauracion_y_escucha(self):
        class Ventana:
            def __init__(self, visible=False, minimizada=False):
                self.visible, self.minimizada, self.llamadas = visible, minimizada, []
                self.contenedora = None
            def isMinimized(self): return self.minimizada
            def isVisible(self): return self.visible
            def window(self): return self.contenedora or self
            def showNormal(self): self.llamadas.append("showNormal"); self.visible = True; self.minimizada = False
            def show(self): self.llamadas.append("show"); self.visible = True
            def hide(self): self.llamadas.append("hide"); self.visible = False
            def raise_(self): self.llamadas.append("raise_")
            def activateWindow(self): self.llamadas.append("activateWindow")
            def update(self): self.llamadas.append("update")

        class Reloj:
            def after(self, _ms, callback): callback()

        class Cara(Ventana):
            def __init__(self):
                super().__init__()
                self.root = Reloj()
                self.contenedora = Ventana(minimizada=True)
                self.estado_escucha = False
            def poner_escuchando(self, valor): self.estado_escucha = valor
            def programar_retorno_neutral(self, _ms): pass

        cara, panel = Cara(), Ventana()
        app = SimpleNamespace(cara=cara, casa=panel, cola=queue.Queue(),
            memoria=SimpleNamespace(creador="Usuario", nombre="Usuario"),
            oido=SimpleNamespace(escuchar=lambda **_kw: None),
            conversacion=False, escuchando=False, descansando=True,
            pendiente_descanso=False, silencios=0, musica_activa=False,
            flujo=None, _generacion_escucha=0, _iniciar_reflexion=lambda: None,
            decir=lambda *_args, **_kw: None)
        app.escuchar = lambda: conversacion.escuchar(app)
        app.despertar = lambda: conversacion.despertar(app)
        cara.hide()
        panel.hide()

        eventos.atender_evento(app, "despertar", None)
        self.assertFalse(app.descansando)
        self.assertTrue(app.conversacion)
        tipo, valor = app.cola.get_nowait()
        self.assertEqual((tipo, valor), ("restaurar_ventanas", None))
        eventos.atender_evento(app, tipo, valor)
        self.assertIn("show", cara.llamadas)
        self.assertIn("showNormal", cara.contenedora.llamadas)
        self.assertTrue(all(x in cara.llamadas for x in ("raise_", "activateWindow", "update")))
        self.assertFalse(any(x in panel.llamadas for x in
            ("show", "showNormal", "raise_", "activateWindow", "update")))

        eventos.atender_evento(app, "fin_voz", None)
        limite = time.time() + 1
        while not app.escuchando and time.time() < limite:
            time.sleep(.005)
        self.assertTrue(app.escuchando)
        self.assertTrue(cara.estado_escucha)
        while not app.cola.empty():
            app.cola.get_nowait()
        conversacion.alternar_conversacion(app, "interfaz")
        conversacion.alternar_conversacion(app, "interfaz")
        self.assertFalse(any(app.cola.get_nowait()[0] == "restaurar_ventanas"
            for _ in range(app.cola.qsize())))
        self.assertFalse(panel.visible)

    def test_casa_tic_interrumpe_y_detiene_timer(self):
        reloj = SimpleNamespace(detener=0, stop=lambda: setattr(reloj, "detener", reloj.detener + 1))
        casa_obj = SimpleNamespace(ventilador=False, reloj=reloj,
            isVisible=lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
        with patch.object(casa.QApplication, "quit") as salir:
            casa.Casa._tic(casa_obj)
        self.assertEqual(reloj.detener, 1)
        salir.assert_called_once_with()

    def test_contexto_vivo_prevalece_y_ventanas_no_se_memorizan(self):
        memoria = SimpleNamespace(
            hechos=["El usuario está trabajando con Visual Studio Code en aprendizaje.py."],
            datos={"resumenes_tematicos": {}}, nombre="Silvestra", creador="Moisés",
            proposito="asistente personal")
        app = SimpleNamespace(sistema_multimodal=SimpleNamespace(
            consultar_entorno_actual=lambda *_: {"ventana": {
                "ejecutable": "Antigravity IDE.exe", "titulo": "Proyecto_Silvestra - memoria_filtro.py"},
                "audio": "sin observaciones", "situacion": "hecho observado",
                "captura_pantalla": "no solicitada"}))
        prompt = Cerebro(None, memoria, app=app).instrucciones("¿Qué archivo tengo abierto ahora?")
        self.assertIn("[ESTADO ACTUAL EN VIVO DE WINDOWS]", prompt)
        self.assertLess(prompt.index("[ESTADO ACTUAL EN VIVO DE WINDOWS]"),
                        prompt.index("Lo que sabes (fechas relativas"))
        regla = prompt[prompt.index("Los recuerdos de memoria a largo plazo"):]
        self.assertIn("EXCLUSIVAMENTE usando [ESTADO ACTUAL EN VIVO DE WINDOWS]", regla)
        self.assertIn("ignora aplicaciones o archivos mencionados en recuerdos pasados", regla)
        self.assertIn("Antigravity IDE.exe", prompt)
        self.assertIn("memoria_filtro.py", prompt)
        for recuerdo in ("El usuario está usando Visual Studio Code ahora.",
                         "El usuario tiene abierto el archivo aprendizaje.py."):
            self.assertFalse(es_recuerdo_valido(recuerdo)[0], recuerdo)
        self.assertTrue(es_recuerdo_valido(
            "El usuario desarrolla proyectos de Python en Visual Studio Code.")[0])

    def test_alternar_con_tts_interrumpido_reanuda_captura(self):
        oido = object.__new__(Oido)
        oido.bloqueo = threading.RLock()
        oido._escuchando_activo = False
        primera = threading.Event()
        llamadas = []

        def capturar(corto=False, app=None, generacion=None):
            llamadas.append(generacion)
            if len(llamadas) == 1:
                primera.set()
                while app._generacion_escucha == generacion:
                    time.sleep(0.005)
                return None
            return "audio listo"

        oido._escuchar = capturar
        app = type("App", (), {})()
        app.memoria = type("Memoria", (), {"nombre": "Usuario"})()
        app.cara = type("Cara", (), {"poner_escuchando": lambda *args: None})()
        app.oido = oido
        app.cola = queue.Queue()
        app.conversacion = False
        app.escuchando = False
        app._generacion_escucha = 0
        app.silencios = 0
        app.musica_activa = False
        app._iniciar_reflexion = lambda: None
        app.locuciones = []

        def decir(frase, *args, **kwargs):
            if app.locuciones:
                app.locuciones[-1] = "interrumpida"
            app.locuciones.append(frase)

        app.decir = decir
        alternar_conversacion(app, "prueba_inicio")
        self.assertTrue(primera.wait(1.0))
        alternar_conversacion(app, "prueba_silencio")
        alternar_conversacion(app, "prueba_reanudar")

        limite = time.time() + 2.0
        eventos = []
        while time.time() < limite and (not eventos or ("oido", "audio listo") not in eventos):
            try:
                eventos.append(app.cola.get(timeout=0.01))
            except queue.Empty:
                pass
        self.assertEqual(eventos.count(("restaurar_ventanas", None)), 0)
        self.assertIn(("oido", "audio listo"), eventos)
        self.assertTrue(app.conversacion)
        self.assertTrue(app.escuchando)
        self.assertEqual(llamadas, [1, 3])
        self.assertIn("interrumpida", app.locuciones)

    def test_final_de_tts_obsoleto_no_decrementa_el_nuevo(self):
        voz = object.__new__(Voz)
        voz.version = 1
        voz._activos = 1
        voz._estado_lock = threading.RLock()
        voz.nivel_volumen = 0.5
        voz._parar = lambda: None
        flujo = Flujo()
        hilo = threading.Thread(target=voz._hablar, args=(flujo, None, 1))
        hilo.start()
        time.sleep(0.05)
        with voz._estado_lock:
            voz.version = 2
            voz._activos = 1
        flujo.cerrar()
        hilo.join(1.0)
        self.assertFalse(hilo.is_alive())
        self.assertEqual(voz._activos, 1)

    def test_calidad_allowlist_toma_todo_el_contexto_de_ventanas(self):
        contexto = [{"role": "system", "content": (
            'Aplicación activa en Windows: Code.exe | Ventana: "VS Code"\n'
            "Contexto multimodal reciente:\nVentanas visibles por orden Z:\n"
            '1. ChatGPT.exe | Ventana: "ChatGPT"\n'
            '2. chrome.exe | Ventana: "Chrome"\n') }]
        respuesta = "Tienes abierto Visual Studio Code, la ventana de ChatGPT y Chrome."
        self.assertTrue(analizar_calidad_texto(respuesta, contexto_windows=contexto)[0])
        self.assertFalse(analizar_calidad_texto("Soy ChatGPT.", contexto_windows=contexto)[0])
        self.assertFalse(analizar_calidad_texto("Como modelo de OpenAI, no puedo.", contexto_windows=contexto)[0])

    def test_hora_local_aclara_medianoche_y_usa_astimezone(self):
        import cerebro_prompt
        convertido = []
        fecha = datetime.datetime(2026, 1, 2, 0, 7, tzinfo=datetime.timezone.utc)

        class Ahora:
            def astimezone(self):
                convertido.append(True)
                return fecha

        class FechaHora:
            @staticmethod
            def now():
                return Ahora()

        with patch.object(cerebro_prompt, "datetime", SimpleNamespace(datetime=FechaHora)):
            hora = cerebro_prompt.obtener_hora_local()
        self.assertTrue(convertido)
        self.assertIn("12:07 a. m.", hora)
        self.assertIn("medianoche / madrugada", hora)


if __name__ == "__main__":
    unittest.main()
