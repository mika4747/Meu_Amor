import io
import json
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import fb_bot


class RespostaFalsa(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def resposta(dados):
    return RespostaFalsa(json.dumps(dados).encode())


class TestCliente(unittest.TestCase):
    def setUp(self):
        self.cliente = fb_bot.ClienteFacebook("111", "TOKEN", "v24.0")

    def _enviado(self, urlopen):
        req = urlopen.call_args[0][0]
        return req, urllib.parse.parse_qs(req.data.decode()) if req.data else {}

    @mock.patch("urllib.request.urlopen")
    def test_publicar_texto(self, urlopen):
        urlopen.return_value = resposta({"id": "111_222"})
        r = self.cliente.publicar("Olá", link="https://x.com")
        req, campos = self._enviado(urlopen)
        self.assertEqual(req.full_url, "https://graph.facebook.com/v24.0/111/feed")
        self.assertEqual(campos["message"], ["Olá"])
        self.assertEqual(campos["link"], ["https://x.com"])
        self.assertEqual(campos["access_token"], ["TOKEN"])
        self.assertNotIn("published", campos)
        self.assertEqual(r["id"], "111_222")

    @mock.patch("urllib.request.urlopen")
    def test_agendar(self, urlopen):
        urlopen.return_value = resposta({"id": "1"})
        quando = datetime.now(timezone.utc) + timedelta(hours=2)
        self.cliente.publicar("Depois", quando=quando)
        _, campos = self._enviado(urlopen)
        self.assertEqual(campos["published"], ["false"])
        self.assertEqual(campos["scheduled_publish_time"], [str(int(quando.timestamp()))])

    @mock.patch("urllib.request.urlopen")
    def test_imagem_por_url_com_link(self, urlopen):
        urlopen.return_value = resposta({"id": "1", "post_id": "111_9"})
        self.cliente.publicar("Foto", link="https://x.com", imagem="https://img/a.jpg")
        req, campos = self._enviado(urlopen)
        self.assertTrue(req.full_url.endswith("/111/photos"))
        self.assertEqual(campos["url"], ["https://img/a.jpg"])
        self.assertEqual(campos["caption"], ["Foto\n\nhttps://x.com"])

    @mock.patch("urllib.request.urlopen")
    def test_imagem_local_multipart(self, urlopen):
        urlopen.return_value = resposta({"id": "1"})
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNGdados")
        self.cliente.publicar("Legenda", imagem=f.name)
        req = urlopen.call_args[0][0]
        self.assertIn("multipart/form-data", req.get_header("Content-type"))
        self.assertIn(b"\x89PNGdados", req.data)
        self.assertIn(b'name="caption"', req.data)
        Path(f.name).unlink()

    def test_post_vazio(self):
        with self.assertRaises(fb_bot.ErroFacebook):
            self.cliente.publicar("")

    @mock.patch("urllib.request.urlopen")
    def test_erro_token(self, urlopen):
        corpo = json.dumps({"error": {"message": "Session expired", "code": 190}}).encode()
        urlopen.side_effect = urllib.error.HTTPError("u", 400, "x", {}, io.BytesIO(corpo))
        with self.assertRaises(fb_bot.ErroFacebook) as ctx:
            self.cliente.verificar()
        self.assertIn("token inválido", str(ctx.exception))

    def test_sem_config(self):
        with self.assertRaises(fb_bot.ErroFacebook):
            fb_bot.ClienteFacebook("", "")


class TestHorario(unittest.TestCase):
    def test_limites(self):
        agora = time.time()
        base = datetime.fromtimestamp(agora, timezone.utc)
        with self.assertRaises(fb_bot.ErroFacebook):
            fb_bot.validar_horario(base + timedelta(minutes=5), agora)
        with self.assertRaises(fb_bot.ErroFacebook):
            fb_bot.validar_horario(base + timedelta(days=31), agora)
        fb_bot.validar_horario(base + timedelta(days=1), agora)

    def test_ler_horario(self):
        dt = fb_bot.ler_horario("2026-12-24T20:00-03:00")
        self.assertEqual(dt.utcoffset(), timedelta(hours=-3))
        self.assertIsNotNone(fb_bot.ler_horario("2026-12-24 20:00").tzinfo)
        with self.assertRaises(fb_bot.ErroFacebook):
            fb_bot.ler_horario("amanhã")


class TestFila(unittest.TestCase):
    def test_agenda_e_nao_duplica(self):
        quando = (datetime.now().astimezone() + timedelta(days=1)).isoformat()
        posts = [{"mensagem": "a", "quando": quando},
                 {"mensagem": "b", "id_facebook": "ja"},
                 {"mensagem": "c", "quando": "ontem"}]
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "posts.json"
            arq.write_text(json.dumps(posts))
            cliente = mock.Mock()
            cliente.publicar.return_value = {"id": "111_1"}
            erros = fb_bot.agendar_arquivo(cliente, arq)
            self.assertEqual(erros, 1)  # "ontem" é inválido
            self.assertEqual(cliente.publicar.call_count, 1)
            salvo = json.loads(arq.read_text())
            self.assertEqual(salvo[0]["id_facebook"], "111_1")

            cliente.reset_mock()
            fb_bot.agendar_arquivo(cliente, arq)
            self.assertEqual(cliente.publicar.call_count, 0)

    def test_simular_nao_envia(self):
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "posts.json"
            arq.write_text(json.dumps([{"mensagem": "x"}]))
            self.assertEqual(fb_bot.agendar_arquivo(None, arq, simular=True), 0)
            self.assertNotIn("id_facebook", arq.read_text())


if __name__ == "__main__":
    unittest.main()
