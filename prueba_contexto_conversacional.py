"""Hilo conversacional continuo (Live/Celeste) y retorno automático a Reposo Azul."""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cara_orbe_hibrido as coh
import cerebro_hilo
import estado
import live_estado
import live_turno
import memoria
import memoria_contexto
import memoria_ficha
import memoria_supabase
import memoria_unificada
import respuesta_flujo

RAIZ = os.path.dirname(os.path.abspath(__file__))


def _limpiar_turnos():
    memoria_contexto.instalar_espejo(None)
    with memoria_contexto._bloqueo:
        memoria_contexto._TURNOS.clear()


def _fuente(nombre):
    with open(os.path.join(RAIZ, nombre), encoding="utf-8") as f:
        return f.read()


def _capturar_autoaprendizaje(modulo):
    """Devuelve (contexto, capturas) para verificar el hilo daemon por turno."""
    capturas = []
    real = memoria_unificada.aprender_del_turno_async

    def capturar(texto, canal="texto"):
        hilo = real(texto, canal)
        capturas.append((texto, canal, hilo))
        return hilo

    return patch.object(memoria_unificada, "aprender_del_turno_async",
                        side_effect=capturar), capturas


class TestAcumulacionLive(unittest.TestCase):
    def setUp(self):
        _limpiar_turnos()

    def tearDown(self):
        _limpiar_turnos()

    def test_fragmentos_parciales_se_guardan_completos(self):
        ac = live_turno.AcumuladorTurnos()
        for parte in ("Hola,", "Hola, ¿cómo", "Hola, ¿cómo estás?"):
            ac.agregar_usuario(parte)
        for parte in ("Estoy", "Estoy bien,", "Estoy bien, ¿y tú?"):
            ac.agregar_kaya(parte)
        self.assertTrue(ac.vaciar())
        self.assertEqual(memoria_contexto.historial_conversacion_activa()[-2:], [
            {"role": "user", "content": "Hola, ¿cómo estás?"},
            {"role": "assistant", "content": "Estoy bien, ¿y tú?"},
        ])
        self.assertFalse(ac.vaciar())

    def test_cfg_se_reconstruye_con_el_hilo_reciente(self):
        memoria_contexto.registrar_turno("user", "Hablemos de Supabase")
        memoria_contexto.registrar_turno("kaya", "Claro, ¿qué parte?")
        with patch("live_turno.live_herramientas.declarar_declaraciones_herramientas",
                   return_value=[]):
            cfg1 = live_turno.construir_config("Kaya", False, False, "Moisés")
            cfg2 = live_turno.construir_config("Kaya", False, False, "Moisés")
        uno = cfg1.system_instruction.parts[0].text
        dos = cfg2.system_instruction.parts[0].text
        for texto in (uno, dos):
            self.assertIn("[Conversación reciente en curso]", texto)
            self.assertIn("Hablemos de Supabase", texto)
            self.assertIn("¿qué parte?", texto)
        self.assertEqual(uno, dos)


class TestHiloCompartido(unittest.TestCase):
    def setUp(self):
        _limpiar_turnos()

    def tearDown(self):
        _limpiar_turnos()

    def test_espejo_y_cambio_live_celeste_conservan_el_hilo(self):
        cerebro = SimpleNamespace(historial=[], _podar_historial=lambda: None)
        memoria_contexto.instalar_espejo(
            lambda rol, texto: cerebro_hilo.reflejar_turno(cerebro.historial, rol, texto)
        )
        memoria_contexto.registrar_turno("user", "Sobre eso de Supabase")
        memoria_contexto.registrar_turno("kaya", "Sí, la consulta lenta.")
        self.assertEqual(cerebro.historial[-2:], [
            {"role": "user", "content": "Sobre eso de Supabase"},
            {"role": "assistant", "content": "Sí, la consulta lenta"},
        ])

        respuesta_flujo._reg_turno(cerebro, "Sígueme contando", "El índice faltaba.")
        historial = memoria_contexto.historial_conversacion_activa()
        contenidos = [h["content"] for h in historial]
        self.assertIn("Sígueme contando", contenidos)
        self.assertIn("El índice faltaba", contenidos)

        mensajes = cerebro_hilo.historial_podado(cerebro.historial)
        self.assertIn("Conversación reciente en curso", mensajes[0]["content"])
        self.assertTrue(any("índice faltaba" in h["content"] for h in mensajes))

    def test_ventana_respeta_doce_turnos_y_mil_cuatrocientos_caracteres(self):
        for i in range(20):
            memoria_contexto.registrar_turno(
                "user" if i % 2 == 0 else "kaya", f"Turno {i} " + ("x" * 80)
            )
        historial = memoria_contexto.historial_conversacion_activa()
        self.assertLessEqual(len(historial), 12)
        self.assertLessEqual(sum(len(h["content"]) for h in historial), 1400)
        self.assertIn("Turno 19", historial[-1]["content"])


class TestReposoAzul(unittest.TestCase):
    def test_umbral_silencio_y_envio_de_estado(self):
        with open(os.path.join(RAIZ, "live_webrtc.py"), encoding="utf-8") as f:
            fuente = f.read()
        self.assertRegex(
            fuente, r"uActivo\s*=\s*Math\.max\(0\.0065\s*,\s*piso\s*\*\s*1\.65\)"
        )
        self.assertIn("ahora-ultimoHabla>9000", fuente)
        self.assertIn("dormida=true", fuente)
        self.assertIn('sendCtrl({type:"estado",v:"reposo"})', fuente)
        self.assertIn("if(!dormida){ws.send", fuente)
        self.assertIn("if(framesVoz>=2)ultimoHabla=ahora", fuente)
        self.assertIn("maxsize=600", fuente)

        # Ruido sostenido por debajo del umbral: el reloj de 9 s avanza solo.
        piso = min(0.007, 0.012 * 0.98 + 0.008 * 0.02)
        umbral = max(0.0065, piso * 1.65)
        self.assertGreater(umbral, 0.008)
        ultimo_habla, ahora, dormida = 0.0, 0.0, False
        for _ in range(91):
            ahora += 100.0
            rms = 0.008
            if rms > umbral:
                ultimo_habla = ahora
            if not dormida and ahora - ultimo_habla > 9000:
                dormida = True
        self.assertTrue(dormida)

        # Habla real por encima del umbral reinicia el reloj y mantiene Live abierto.
        for _ in range(2):
            ahora += 50.0
            if 0.02 > umbral:
                ultimo_habla = ahora
        self.assertEqual(ultimo_habla, ahora)

    def test_orbe_interpola_hacia_azul_profundo_con_micro_cerrado(self):
        cara = SimpleNamespace(
            voz_silenciada=False, baile_hasta=0.0, hablando=True, escuchando=True,
            pensando=False, pensando_hasta=0.0, nivel_volumen=0.0,
            micro_live_cerrado=True, estado_live="reposo",
        )
        orbe = coh.GestorOrbeHibrido()
        self.assertEqual(orbe.deducir_estado(cara), "reposo")
        for i in range(80):
            orbe.actualizar(cara, t=float(i) * 0.016, nivel_rms=0.0)
        paleta = coh.PALETAS["reposo"]
        self.assertEqual(set(paleta), {
            "centro", "medio", "borde", "halo", "acento",
            "plasma1", "plasma2", "plasma3",
        })
        self.assertEqual(paleta["medio"].name(), "#1d4ed8")
        self.assertEqual(paleta["plasma2"].name(), "#3b82f6")
        self.assertLess(
            abs(orbe._colores_suaves["medio"].blue() - paleta["medio"].blue()), 6
        )
        self.assertLess(
            abs(orbe._colores_suaves["plasma2"].green() - paleta["plasma2"].green()), 6
        )
        cara.micro_live_cerrado = False
        cara.hablando = cara.escuchando = False
        self.assertEqual(orbe.deducir_estado(cara), "reposo")


class TestMemoriaDesdeArranque(unittest.TestCase):
    """Migración, ficha visible, auto-aprendizaje e hilo compartido."""

    def setUp(self):
        _limpiar_turnos()
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta_estado = os.path.join(self.tmp.name, "estado.json")
        self.parche_estado = patch.object(estado, "RUTA", self.ruta_estado)
        self.parche_estado.start()
        estado.guardar({})
        self.parche_env = patch.object(memoria_supabase, "_leer_env", return_value={})
        self.parche_env.start()
        memoria_supabase.reiniciar_para_pruebas()
        memoria_unificada._sincronizados.clear()
        self.instancia_original = memoria._memoria_instancia
        self.ruta_json = os.path.join(self.tmp.name, "memoria.json")
        with open(self.ruta_json, "w", encoding="utf-8") as f:
            json.dump({
                "nombre": "Ana", "creador": "Ana", "proposito": "ayudar",
                "hechos": ["A Ana le gusta la comida italiana"],
                "resumenes_tematicos": {},
            }, f, ensure_ascii=False)
        self.mem = memoria.Memoria(
            ruta_db=os.path.join(self.tmp.name, "memoria.db"),
            ruta_json=self.ruta_json, usuario_id="prueba_contexto",
        )
        self.mem.nacer("Kaya", "Ana", "ayudar")
        memoria_contexto.resetear_sesion()

    def tearDown(self):
        self.mem.cerrar()
        memoria._memoria_instancia = self.instancia_original
        memoria_supabase.reiniciar_para_pruebas()
        self.parche_env.stop()
        self.parche_estado.stop()
        self.tmp.cleanup()
        _limpiar_turnos()

    def test_migracion_ficha_y_autoaprendizaje_live_y_celeste(self):
        self.assertEqual(memoria_contexto.usuario_id_canonical(), "prueba_contexto")
        self.assertIn("italiana", memoria_unificada.consultar("italiana"))
        resumen = memoria_contexto.resumen_para_prompt()
        self.assertIn("[Ficha:", resumen)
        self.assertIn("Ana", resumen)
        self.assertIn("italiana", resumen)

        with patch("live_turno.live_herramientas.declarar_declaraciones_herramientas",
                   return_value=[]):
            cfg = live_turno.construir_config("Kaya", False, False, "Ana")
        instruccion = cfg.system_instruction.parts[0].text
        self.assertIn("[Ficha y recuerdos del usuario]", instruccion)
        self.assertIn("Ana", instruccion)

        acumulador = live_turno.AcumuladorTurnos()
        acumulador.agregar_usuario(
            "Hola, me llamo Ana y estudio Ingeniería Industrial en la Universidad de Panamá. "
            "Me gusta la comida italiana."
        )
        acumulador.agregar_kaya("Qué bien, Ana.")
        parche, capturas = _capturar_autoaprendizaje(live_turno)
        with parche:
            acumulador.vaciar()
        self.assertTrue(capturas)
        for _texto, _canal, hilo in capturas:
            hilo.join(3)
        self.assertIn("Ingeniería", memoria_unificada.consultar("Ingeniería"))
        self.assertIn("Estudios: Ingeniería Industrial", memoria_ficha.resumen())

        parche, capturas = _capturar_autoaprendizaje(memoria_contexto)
        with parche:
            memoria_contexto.registrar_par(
                "Trabajo en el proyecto Aurora y vivo en David.", "Bien.")
        self.assertTrue(capturas)
        for _texto, _canal, hilo in capturas:
            hilo.join(3)
        self.assertIn("Aurora", memoria_unificada.consultar("Aurora"))
        self.assertIn("Aurora", memoria_ficha.resumen())

    def test_doce_turnos_tras_reconexion_y_cambio_live_celeste(self):
        for i in range(14):
            memoria_contexto.registrar_turno(
                "user" if i % 2 == 0 else "kaya", f"Turno {i} " + ("x" * 30))
        with patch("live_turno.live_herramientas.declarar_declaraciones_herramientas",
                   return_value=[]):
            cfg1 = live_turno.construir_config("Kaya", False, False, "Ana")
            cfg2 = live_turno.construir_config("Kaya", False, False, "Ana")
        textos = [cfg.system_instruction.parts[0].text for cfg in (cfg1, cfg2)]
        for texto in textos:
            self.assertIn("[Ficha y recuerdos del usuario]", texto)
            self.assertIn("[Conversación reciente en curso]", texto)
            self.assertIn("Turno 13", texto)
        self.assertNotIn("Turno 0 ", textos[1])

        cerebro = SimpleNamespace(historial=[], _podar_historial=lambda: None)
        memoria_contexto.instalar_espejo(
            lambda rol, texto: cerebro_hilo.reflejar_turno(cerebro.historial, rol, texto))
        for i in range(14, 16):
            memoria_contexto.registrar_turno(
                "user" if i % 2 == 0 else "kaya", f"Turno {i} " + ("y" * 30))
        mensajes = cerebro_hilo.historial_podado(cerebro.historial)
        sistemas = [m["content"] for m in mensajes if m["role"] == "system"]
        self.assertTrue(any("Ficha y recuerdos del usuario" in s for s in sistemas))
        self.assertTrue(any("Conversación reciente en curso" in s for s in sistemas))
        self.assertTrue(any("Turno 15" in m["content"] for m in mensajes))
        self.assertLessEqual(len(memoria_contexto.historial_conversacion_activa()), 12)


class TestTurnosLargosSinBloqueo(unittest.TestCase):
    """Intervenciones de 15-45 s sin descartes ni estados colgados."""

    def setUp(self):
        _limpiar_turnos()

    def tearDown(self):
        _limpiar_turnos()

    def test_config_live_y_oido_aceptan_pausas_y_segmentos_de_45s(self):
        self.assertIn("maxsize=600", _fuente("live_webrtc.py"))
        audio = _fuente("live_audio.py")
        for marca in ("AutomaticActivityDetection", "realtime_input_config",
                      "silence_duration_ms=1100", "prefix_padding_ms=300"):
            self.assertIn(marca, audio)
        oido = _fuente("oido.py")
        self.assertIn("max_habla_segundos = 45.0", oido)
        self.assertIn("timeout=30.0", oido)
        vad = _fuente("oido_vad.py")
        self.assertIn("max_speech_duration=45.0", vad)
        self.assertIn("buffer_size=60.0", vad)
        self.assertIn("maxsize=1000", _fuente("oido_flujo.py"))
        self.assertIn("TIMEOUT = 30.0", _fuente("oido_deepgram.py"))
        self.assertGreaterEqual(
            _fuente("live_motor.py").count("live_estado.reanudar_escucha(self)"), 3)

    def test_fragmentos_largos_y_reanudacion_de_estado(self):
        partes = [f"Frase{i:02d}" for i in range(45)]
        acumulador = live_turno.AcumuladorTurnos()
        for parte in partes:
            acumulador.agregar_usuario(parte)
        acumulador.agregar_kaya("Te escucho completo.")
        parche, capturas = _capturar_autoaprendizaje(live_turno)
        with parche:
            acumulador.vaciar()
        self.assertTrue(capturas)
        for _texto, _canal, hilo in capturas:
            hilo.join(3)
        historial = memoria_contexto.historial_conversacion_activa()
        usuario = next(h["content"] for h in historial if h["role"] == "user")
        for parte in partes:
            self.assertIn(parte, usuario)

        estados = []
        sesion = SimpleNamespace(
            _notificar_estado=estados.append,
            puerta=SimpleNamespace(notificar_actividad=lambda: None),
            _puente_webrtc=None,
        )
        self.assertTrue(live_estado.reanudar_escucha(sesion))
        self.assertEqual(estados, ["escuchando"])
        estados.clear()
        sesion._puente_webrtc = SimpleNamespace(dormida=True)
        self.assertFalse(live_estado.reanudar_escucha(sesion))
        self.assertEqual(estados, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
