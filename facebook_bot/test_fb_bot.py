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


PAGINAS = [{"id": "111", "nome": "Meu Amor", "token": "T1", "padrao": True},
           {"id": "222", "nome": "Loja", "token": "T2"}]


def conta_falsa(clientes=None):
    """Conta com duas Páginas; clientes = {id: Mock}. Devolve (conta, clientes)."""
    clientes = clientes or {}
    for p in PAGINAS:
        clientes.setdefault(p["id"], mock.Mock())
    paginas = [dict(p) for p in PAGINAS]
    return fb_bot.Conta(paginas, fabrica=lambda p: clientes[p["id"]]), clientes


class TestConta(unittest.TestCase):
    def test_resolver(self):
        conta, _ = conta_falsa()
        self.assertEqual([p["id"] for p in conta.resolver(None)], ["111"])
        self.assertEqual([p["id"] for p in conta.resolver("loja")], ["222"])
        self.assertEqual([p["id"] for p in conta.resolver("Loja, 111")], ["222", "111"])
        self.assertEqual([p["id"] for p in conta.resolver(["Todas"])], ["111", "222"])
        self.assertEqual([p["id"] for p in conta.resolver(["Loja", "loja"])], ["222"])
        with self.assertRaises(fb_bot.ErroFacebook) as ctx:
            conta.resolver("Outra")
        self.assertIn("Meu Amor, Loja", str(ctx.exception))

    def test_sem_paginas(self):
        with self.assertRaises(fb_bot.ErroFacebook):
            fb_bot.Conta([]).resolver(None)
        with self.assertRaises(fb_bot.ErroFacebook):
            fb_bot.Conta([]).resolver("todas")

    def test_padrao_e_salvar(self):
        conta, _ = conta_falsa()
        conta.definir_padrao("Loja")
        self.assertEqual(conta.padrao()["nome"], "Loja")
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "paginas.json"
            conta.salvar(arq)
            self.assertEqual(arq.stat().st_mode & 0o777, 0o600)
            relida = fb_bot.Conta.do_ambiente(arq)
            self.assertEqual(relida.padrao()["id"], "222")

    def test_env_antigo_vira_pagina_unica(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(
                "os.environ", {"FB_PAGE_ID": "9", "FB_PAGE_ACCESS_TOKEN": "TK"}):
            conta = fb_bot.Conta.do_ambiente(Path(d) / "nao_existe.json")
        self.assertEqual(conta.padrao()["token"], "TK")


class TestFila(unittest.TestCase):
    def test_agenda_e_nao_duplica(self):
        quando = (datetime.now().astimezone() + timedelta(days=1)).isoformat()
        posts = [{"mensagem": "a", "quando": quando},
                 {"mensagem": "b", "id_facebook": "ja"},   # formato antigo
                 {"mensagem": "c", "quando": "ontem"}]
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "posts.json"
            arq.write_text(json.dumps(posts))
            conta, cli = conta_falsa()
            cli["111"].publicar.return_value = {"id": "111_1"}
            erros = fb_bot.agendar_arquivo(conta, arq)
            cli["111"].publicar.assert_called_once_with("a", None, [], None, mock.ANY)
            cli["222"].publicar.assert_not_called()  # sem "paginas": só a padrão
            self.assertEqual(erros, 1)  # "ontem" é inválido
            salvo = json.loads(arq.read_text())
            self.assertEqual(salvo[0]["enviados"], {"111": "111_1"})

            cli["111"].reset_mock()
            fb_bot.agendar_arquivo(conta, arq)
            cli["111"].publicar.assert_not_called()

    def test_varias_paginas_e_reenvio_so_da_que_falhou(self):
        quando = (datetime.now().astimezone() + timedelta(days=1)).isoformat()
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "posts.json"
            arq.write_text(json.dumps([
                {"mensagem": "todas", "quando": quando, "paginas": "todas"},
                {"mensagem": "só loja", "quando": quando, "paginas": ["Loja"]},
                {"mensagem": "errada", "paginas": "Inexistente"},
            ]))
            conta, cli = conta_falsa()
            cli["111"].publicar.return_value = {"id": "111_A"}
            cli["222"].publicar.side_effect = [fb_bot.ErroFacebook("fora do ar"),
                                               {"id": "222_B"}]
            erros = fb_bot.agendar_arquivo(conta, arq)
            self.assertEqual(erros, 2)  # Loja falhou no 1º + Página inexistente
            salvo = json.loads(arq.read_text())
            self.assertEqual(salvo[0]["enviados"], {"111": "111_A"})
            self.assertEqual(salvo[1]["enviados"], {"222": "222_B"})
            self.assertNotIn("enviados", salvo[2])

            # segunda rodada: só a Loja do 1º post é tentada de novo
            cli["111"].reset_mock()
            cli["222"].publicar.side_effect = None
            cli["222"].publicar.return_value = {"id": "222_A"}
            fb_bot.agendar_arquivo(conta, arq)
            cli["111"].publicar.assert_not_called()
            self.assertEqual(cli["222"].publicar.call_count, 3)  # 2 na 1ª rodada + 1
            self.assertEqual(cli["222"].publicar.call_args_list[-1][0][0], "todas")
            salvo = json.loads(arq.read_text())
            self.assertEqual(salvo[0]["enviados"], {"111": "111_A", "222": "222_A"})

    def test_simular_nao_envia(self):
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "posts.json"
            arq.write_text(json.dumps([{"mensagem": "x", "paginas": "Loja"}]))
            self.assertEqual(fb_bot.agendar_arquivo(None, arq, simular=True), 0)
            conta, cli = conta_falsa()
            self.assertEqual(fb_bot.agendar_arquivo(conta, arq, simular=True), 0)
            cli["222"].publicar.assert_not_called()
            self.assertNotIn("enviados", arq.read_text())


class TestLegenda(unittest.TestCase):
    def test_normalizar(self):
        self.assertEqual(fb_bot.normalizar_hashtags(["amor", "#Viagem"], "viagem, #foto praia"),
                         ["#amor", "#Viagem", "#foto", "#praia"])
        self.assertEqual(fb_bot.normalizar_hashtags(None, "", []), [])

    def test_montar(self):
        self.assertEqual(fb_bot.montar_legenda("Oi", ["#a", "#b"], "Siga!"),
                         "Oi\n\nSiga!\n\n#a #b")
        # não repete hashtag que já está no texto
        self.assertEqual(fb_bot.montar_legenda("Muito #amor!", ["#amor", "#x"]),
                         "Muito #amor!\n\n#x")
        self.assertEqual(fb_bot.montar_legenda("", ["#a"]), "#a")
        self.assertEqual(fb_bot.montar_legenda("Só texto"), "Só texto")


def _calendario(d, **extra):
    dados = {"horarios": ["19:00", "09:00"], "fuso": "-03:00", **extra}
    arq = Path(d) / "calendario.json"
    arq.write_text(json.dumps(dados))
    return fb_bot.carregar_calendario(arq)


BRT = timezone(timedelta(hours=-3))
# Sábado, 07/11/2026, 10:00 em Brasília
AGORA = datetime(2026, 11, 7, 10, 0, tzinfo=BRT)


class TestCalendario(unittest.TestCase):
    def test_proximos_horarios(self):
        with tempfile.TemporaryDirectory() as d:
            cal = _calendario(d)
        horarios = list(fb_bot.proximos_horarios(cal, set(), AGORA))
        self.assertEqual(horarios[0], datetime(2026, 11, 7, 19, 0, tzinfo=BRT))
        self.assertEqual(horarios[1], datetime(2026, 11, 8, 9, 0, tzinfo=BRT))
        self.assertLessEqual(horarios[-1], AGORA + timedelta(days=30))
        self.assertGreater(len(horarios), 55)

    def test_dias_e_ocupados(self):
        with tempfile.TemporaryDirectory() as d:
            cal = _calendario(d, horarios=["09:00"], dias=["seg", "Quarta"])
        ocupado = int(datetime(2026, 11, 9, 9, 0, tzinfo=BRT).timestamp())
        gerador = fb_bot.proximos_horarios(cal, {ocupado}, AGORA)
        self.assertEqual(next(gerador), datetime(2026, 11, 11, 9, 0, tzinfo=BRT))  # qua
        self.assertEqual(next(gerador), datetime(2026, 11, 16, 9, 0, tzinfo=BRT))  # seg

    def test_horario_muito_proximo_e_pulado(self):
        with tempfile.TemporaryDirectory() as d:
            cal = _calendario(d, horarios=["10:10", "11:00"])
        self.assertEqual(next(fb_bot.proximos_horarios(cal, set(), AGORA)),
                         datetime(2026, 11, 7, 11, 0, tzinfo=BRT))

    def test_calendario_invalido(self):
        with tempfile.TemporaryDirectory() as d:
            for ruim in ({"horarios": []}, {"horarios": ["25h"]},
                         {"horarios": ["09:00"], "dias": ["xyz"]},
                         {"horarios": ["09:00"], "fuso": "Lua/Base"}):
                arq = Path(d) / "c.json"
                arq.write_text(json.dumps(ruim))
                with self.assertRaises(fb_bot.ErroFacebook):
                    fb_bot.carregar_calendario(arq)

    def test_agendar_com_calendario(self):
        agora = datetime.now(BRT).replace(second=0, microsecond=0)
        with tempfile.TemporaryDirectory() as d:
            cal = _calendario(d, hashtags=["amor"], assinatura="Siga!")
            arq = Path(d) / "posts.json"
            marcado = (agora + timedelta(days=2)).replace(hour=12, minute=0)
            arq.write_text(json.dumps([
                {"mensagem": "um", "hashtags": "#extra"},
                {"mensagem": "dois"},
                {"mensagem": "marcado", "quando": marcado.isoformat()},
                {"mensagem": "falha"},
            ]))
            conta, cli = conta_falsa()
            cliente = cli["111"]
            cliente.publicar.side_effect = [{"id": "p1"}, {"id": "p2"}, {"id": "p3"},
                                            fb_bot.ErroFacebook("recusado")]
            erros = fb_bot.agendar_arquivo(conta, arq, calendario=cal)
            self.assertEqual(erros, 1)
            chamadas = cliente.publicar.call_args_list
            self.assertEqual(chamadas[0][0][0], "um\n\nSiga!\n\n#amor #extra")
            self.assertEqual(chamadas[1][0][0], "dois\n\nSiga!\n\n#amor")
            q1, q2 = chamadas[0][0][4], chamadas[1][0][4]
            self.assertLess(q1, q2)
            self.assertIn(q1.astimezone(BRT).hour, (9, 19))
            salvo = json.loads(arq.read_text())
            self.assertEqual(salvo[0]["quando"], q1.isoformat(timespec="minutes"))
            self.assertEqual(salvo[2]["quando"], marcado.isoformat())  # não mexe
            self.assertNotIn("quando", salvo[3])  # falhou: horário liberado
            self.assertEqual(salvo[0]["mensagem"], "um")  # texto original preservado


class TestConectar(unittest.TestCase):
    ESCOPOS = ["pages_show_list", "pages_read_engagement", "pages_manage_posts"]

    @mock.patch("urllib.request.urlopen")
    def test_conecta_todas_as_paginas_com_paginacao(self, urlopen):
        urlopen.side_effect = [
            resposta({"access_token": "LONGO"}),
            resposta({"data": [{"id": "1", "name": "A", "access_token": "TA"}],
                      "paging": {"next": "https://graph.facebook.com/v24.0/me/accounts"
                                         "?after=XYZ&access_token=LONGO"}}),
            resposta({"data": [{"id": "2", "name": "B", "access_token": "TB"}]}),
            resposta({"data": {"expires_at": 0, "scopes": self.ESCOPOS}}),
            resposta({"data": {"expires_at": 0, "scopes": ["pages_show_list"]}}),
        ]
        paginas = fb_bot.obter_paginas("APP", "SEGREDO", "CURTO")
        self.assertEqual([(p["id"], p["nome"], p["token"]) for p in paginas],
                         [("1", "A", "TA"), ("2", "B", "TB")])
        self.assertEqual(paginas[0]["faltando"], [])
        self.assertEqual(paginas[1]["faltando"],
                         ["pages_read_engagement", "pages_manage_posts"])
        urls = [c[0][0].full_url for c in urlopen.call_args_list]
        q = urllib.parse.parse_qs(urllib.parse.urlparse(urls[0]).query)
        self.assertEqual(q["fb_exchange_token"], ["CURTO"])
        self.assertIn("access_token=LONGO", urls[1])
        self.assertIn("after=XYZ", urls[2])
        self.assertIn("input_token=TA", urls[3])
        self.assertIn("input_token=TB", urls[4])

    @mock.patch("urllib.request.urlopen")
    def test_sem_paginas(self, urlopen):
        urlopen.side_effect = [resposta({"access_token": "L"}), resposta({"data": []})]
        with self.assertRaises(fb_bot.ErroFacebook):
            fb_bot.obter_paginas("APP", "S", "C")

    def test_comando_conectar_salva_todas_e_pergunta_a_padrao(self):
        encontradas = [
            {"id": "1", "nome": "A", "token": "TA", "expira": 0, "faltando": []},
            {"id": "2", "nome": "B", "token": "TB", "expira": 0, "faltando": []},
        ]
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(fb_bot, "ARQUIVO_PAGINAS", Path(d) / "paginas.json"), \
                mock.patch.object(fb_bot, "carregar_env"), \
                mock.patch.object(fb_bot, "obter_paginas", return_value=encontradas), \
                mock.patch("builtins.input", return_value="123"), \
                mock.patch("getpass.getpass", side_effect=["seg", "tok"]), \
                mock.patch.dict("os.environ", {}, clear=True), \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            rc = fb_bot.comando_conectar(escolher=lambda nomes, pergunta: 1)
            salvo = json.loads((Path(d) / "paginas.json").read_text())
            # reconectar mantém a padrão escolhida antes, sem perguntar de novo
            with mock.patch("getpass.getpass", side_effect=["seg", "tok"]):
                fb_bot.comando_conectar(escolher=lambda *a: self.fail("não devia perguntar"))
            salvo2 = json.loads((Path(d) / "paginas.json").read_text())
        self.assertEqual(rc, 0)
        self.assertEqual([(p["nome"], p["token"], p["padrao"]) for p in salvo],
                         [("A", "TA", False), ("B", "TB", True)])
        self.assertEqual(salvo2, salvo)

    def test_salvar_env_preserva_linhas(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text("# comentario\nFB_PAGE_ID=velho\nFB_GRAPH_VERSION=v24.0\n")
            fb_bot.salvar_env({"FB_PAGE_ID": "novo", "FB_PAGE_ACCESS_TOKEN": "tok"}, env)
            self.assertEqual(env.read_text(), "# comentario\nFB_PAGE_ID=novo\n"
                             "FB_GRAPH_VERSION=v24.0\nFB_PAGE_ACCESS_TOKEN=tok\n")

if __name__ == "__main__":
    unittest.main()
