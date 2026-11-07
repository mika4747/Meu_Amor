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
        self.cliente.publicar("Foto", link="https://x.com", imagens="https://img/a.jpg")
        req, campos = self._enviado(urlopen)
        self.assertTrue(req.full_url.endswith("/111/photos"))
        self.assertEqual(campos["url"], ["https://img/a.jpg"])
        self.assertEqual(campos["caption"], ["Foto\n\nhttps://x.com"])

    @mock.patch("urllib.request.urlopen")
    def test_imagem_local_multipart(self, urlopen):
        urlopen.return_value = resposta({"id": "1"})
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNGdados")
        self.cliente.publicar("Legenda", imagens=[f.name])
        req = urlopen.call_args[0][0]
        self.assertIn("multipart/form-data", req.get_header("Content-type"))
        self.assertIn(b"\x89PNGdados", req.data)
        self.assertIn(b'name="caption"', req.data)
        Path(f.name).unlink()

    @mock.patch("urllib.request.urlopen")
    def test_varias_fotos_agendadas(self, urlopen):
        urlopen.side_effect = [resposta({"id": "f1"}), resposta({"id": "f2"}),
                               resposta({"id": "111_post"})]
        quando = datetime.now(timezone.utc) + timedelta(days=1)
        r = self.cliente.publicar("Álbum", imagens=["https://a/1.jpg", "https://a/2.jpg"],
                                  quando=quando)
        chamadas = [c[0][0] for c in urlopen.call_args_list]
        foto1 = urllib.parse.parse_qs(chamadas[0].data.decode())
        self.assertEqual(foto1["published"], ["false"])
        self.assertEqual(foto1["temporary"], ["true"])
        self.assertTrue(chamadas[2].full_url.endswith("/111/feed"))
        feed = urllib.parse.parse_qs(chamadas[2].data.decode())
        self.assertEqual(json.loads(feed["attached_media[0]"][0]), {"media_fbid": "f1"})
        self.assertEqual(json.loads(feed["attached_media[1]"][0]), {"media_fbid": "f2"})
        self.assertEqual(feed["message"], ["Álbum"])
        self.assertEqual(feed["scheduled_publish_time"], [str(int(quando.timestamp()))])
        self.assertEqual(r["id"], "111_post")

    @mock.patch("urllib.request.urlopen")
    def test_reel_local(self, urlopen):
        urlopen.side_effect = [
            resposta({"video_id": "v1", "upload_url": "https://rupload.facebook.com/x/v1"}),
            resposta({"success": True}),
            resposta({"success": True}),
        ]
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"videobytes")
        r = self.cliente.publicar("Meu reel", link="https://x.com", reel=f.name)
        Path(f.name).unlink()
        inicio, envio, fim = [c[0][0] for c in urlopen.call_args_list]
        self.assertTrue(inicio.full_url.endswith("/111/video_reels"))
        self.assertEqual(urllib.parse.parse_qs(inicio.data.decode())["upload_phase"], ["start"])
        self.assertEqual(envio.full_url, "https://rupload.facebook.com/x/v1")
        self.assertEqual(envio.get_header("Authorization"), "OAuth TOKEN")
        self.assertEqual(envio.get_header("File_size"), "10")
        self.assertEqual(envio.data, b"videobytes")
        campos = urllib.parse.parse_qs(fim.data.decode())
        self.assertEqual(campos["upload_phase"], ["finish"])
        self.assertEqual(campos["video_id"], ["v1"])
        self.assertEqual(campos["video_state"], ["PUBLISHED"])
        self.assertEqual(campos["description"], ["Meu reel\n\nhttps://x.com"])
        self.assertEqual(r["id"], "v1")

    @mock.patch("urllib.request.urlopen")
    def test_reel_por_url_agendado(self, urlopen):
        urlopen.side_effect = [resposta({"video_id": "v2"}), resposta({"success": True}),
                               resposta({"success": True})]
        quando = datetime.now(timezone.utc) + timedelta(hours=3)
        self.cliente.publicar("", reel="https://cdn/v.mp4", quando=quando)
        _, envio, fim = [c[0][0] for c in urlopen.call_args_list]
        self.assertEqual(envio.full_url,
                         "https://rupload.facebook.com/video-upload/v24.0/v2")
        self.assertEqual(envio.get_header("File_url"), "https://cdn/v.mp4")
        campos = urllib.parse.parse_qs(fim.data.decode())
        self.assertEqual(campos["video_state"], ["SCHEDULED"])
        self.assertEqual(campos["scheduled_publish_time"], [str(int(quando.timestamp()))])

    @mock.patch("urllib.request.urlopen")
    def test_reel_horario_invalido_nao_envia_nada(self, urlopen):
        quando = datetime.now(timezone.utc) + timedelta(minutes=2)
        with self.assertRaises(fb_bot.ErroFacebook):
            self.cliente.publicar("", reel="https://cdn/v.mp4", quando=quando)
        urlopen.assert_not_called()

    def test_reel_com_imagem(self):
        with self.assertRaises(fb_bot.ErroFacebook):
            self.cliente.publicar("x", imagens=["a.jpg"], reel="v.mp4")

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


class TestImagensDoPost(unittest.TestCase):
    def test_formatos(self):
        self.assertEqual(fb_bot._imagens_do_post({"imagem": "a"}), ["a"])
        self.assertEqual(fb_bot._imagens_do_post({"imagens": ["a", "b"]}), ["a", "b"])
        self.assertEqual(fb_bot._imagens_do_post({"imagens": "a"}), ["a"])
        self.assertEqual(fb_bot._imagens_do_post({}), [])


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
            cliente.publicar.assert_called_once_with("a", None, [], None, mock.ANY)
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
