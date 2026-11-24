"""Regresión extraída: keyterm de Deepgram y reintento sin impulso."""
import os
import unittest
from unittest.mock import Mock, patch

import oido_deepgram


class RespuestaDG:
    def __init__(self, codigo, texto="Lyris, abre el bloc", duracion=1.0):
        self.status_code = codigo
        self._texto, self._duracion = texto, duracion

    def json(self):
        return {"metadata": {"duration": self._duracion}, "results": {
            "channels": [{"alternatives": [{"transcript": self._texto}]}]}}


class TestKeytermDeepgram(unittest.TestCase):
    def test_impulso_keyterm_en_deepgram_y_reintento_sin_el(self):
        oido_deepgram.reiniciar()
        self.addCleanup(oido_deepgram.reiniciar)
        for parche in (
                patch.object(oido_deepgram.config, "DEEPGRAM_API_KEY", "", create=True),
                patch.object(oido_deepgram.config, "DEEPGRAM_MODEL", "", create=True),
                patch.dict(os.environ, {"DEEPGRAM_API_KEY": "prueba-keyterm",
                                        "DEEPGRAM_MODEL": "nova-3"})):
            parche.start()
            self.addCleanup(parche.stop)
        with patch.object(oido_deepgram.httpx, "post",
                          Mock(return_value=RespuestaDG(200))) as post:
            resultado = oido_deepgram.transcribir(b"RIFFfalso")
        params = post.call_args.kwargs["params"]
        self.assertEqual((resultado[0], params["model"], params["language"],
                          params["keyterm"]),
                         ("Lyris, abre el bloc", "nova-3", "es", "Lyris:5"))
        with patch.dict(os.environ, {"LYRIS_DEEPGRAM_LANG": "multi"}), \
                patch.object(oido_deepgram.httpx, "post",
                             Mock(return_value=RespuestaDG(200))) as post_multi:
            oido_deepgram.transcribir(b"RIFFfalso")
        self.assertEqual(post_multi.call_args.kwargs["params"]["language"], "multi")

        post = Mock(side_effect=[RespuestaDG(400), RespuestaDG(200)])
        with patch.object(oido_deepgram.httpx, "post", post):
            resultado = oido_deepgram.transcribir(b"RIFFfalso")
        self.assertEqual((resultado[0], post.call_count), ("Lyris, abre el bloc", 2))
        self.assertEqual(post.call_args_list[0].kwargs["params"]["keyterm"], "Lyris:5")
        self.assertNotIn("keyterm", post.call_args_list[1].kwargs["params"])
        self.assertTrue(oido_deepgram.esta_activo())


if __name__ == "__main__":
    unittest.main()
