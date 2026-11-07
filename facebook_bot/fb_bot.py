#!/usr/bin/env python3
"""Bot de postagem para Páginas do Facebook (Graph API): textos, fotos e Reels.

Uso:
    python fb_bot.py publicar "Texto" [--link URL] [--imagem ARQ_OU_URL ...] [--quando DATA]
    python fb_bot.py publicar "Legenda" --reel VIDEO.mp4 [--quando DATA]
    python fb_bot.py agendar posts.json [--simular]
    python fb_bot.py status ID_DO_REEL
    python fb_bot.py verificar

Configuração (variáveis de ambiente ou arquivo .env na mesma pasta):
    FB_PAGE_ID            ID numérico da Página
    FB_PAGE_ACCESS_TOKEN  Token de acesso da Página (não o token de usuário)
    FB_GRAPH_VERSION      Opcional, padrão "v24.0"

Só usa a biblioteca padrão do Python (3.9+).
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

PASTA = Path(__file__).resolve().parent
VERSAO_PADRAO = "v24.0"
# O Facebook exige que posts agendados sejam marcados para pelo menos 10 minutos
# no futuro e no máximo cerca de 30 dias à frente.
AGENDAMENTO_MINIMO_S = 10 * 60
AGENDAMENTO_MAXIMO_S = 30 * 24 * 60 * 60


class ErroFacebook(Exception):
    """Erro devolvido pela Graph API ou pela configuração do bot."""


# ---------------------------------------------------------------- configuração

def carregar_env(caminho: Path = PASTA / ".env") -> None:
    """Lê um arquivo .env simples (CHAVE=valor) sem sobrescrever o ambiente."""
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


def _e_url(texto: str) -> bool:
    return texto.startswith(("http://", "https://"))


def _arquivo_local(caminho: str, tipo: str) -> Path:
    p = Path(caminho).expanduser()
    if not p.is_absolute() and not p.exists():
        p = PASTA / p  # permite caminhos relativos à pasta do bot
    if not p.is_file():
        raise ErroFacebook(f"{tipo} não encontrado(a): {caminho}")
    return p


class ClienteFacebook:
    def __init__(self, page_id: str, token: str, versao: str = VERSAO_PADRAO):
        if not page_id or not token:
            raise ErroFacebook(
                "Defina FB_PAGE_ID e FB_PAGE_ACCESS_TOKEN (veja facebook_bot/README.md)."
            )
        self.page_id = page_id
        self.token = token
        self.versao = versao
        self.base = f"https://graph.facebook.com/{versao}"

    @classmethod
    def do_ambiente(cls) -> "ClienteFacebook":
        carregar_env()
        return cls(
            os.environ.get("FB_PAGE_ID", ""),
            os.environ.get("FB_PAGE_ACCESS_TOKEN", ""),
            os.environ.get("FB_GRAPH_VERSION", VERSAO_PADRAO),
        )

    # ------------------------------------------------------------- HTTP

    @staticmethod
    def _enviar(req: urllib.request.Request, timeout: int = 60) -> dict:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            raise ErroFacebook(_mensagem_de_erro(e)) from None
        except urllib.error.URLError as e:
            raise ErroFacebook(f"Falha de conexão com o Facebook: {e.reason}") from None

    def _requisicao(self, metodo: str, caminho: str, campos: dict | None = None,
                    arquivo: Path | None = None) -> dict:
        campos = {k: v for k, v in (campos or {}).items() if v is not None}
        campos["access_token"] = self.token
        url = f"{self.base}/{caminho}"

        if metodo == "GET":
            req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(campos)}")
        elif arquivo is not None:
            corpo, tipo = _multipart(campos, "source", arquivo)
            req = urllib.request.Request(url, data=corpo, method="POST",
                                         headers={"Content-Type": tipo})
        else:
            corpo = urllib.parse.urlencode({k: str(v) for k, v in campos.items()}).encode()
            req = urllib.request.Request(url, data=corpo, method="POST")
        return self._enviar(req, timeout=300 if arquivo else 60)

    # ------------------------------------------------------------- ações

    def verificar(self) -> dict:
        """Confirma que o token funciona e devolve o nome da Página."""
        return self._requisicao("GET", self.page_id, {"fields": "id,name"})

    def status_video(self, video_id: str) -> dict:
        """Situação do processamento/publicação de um Reel."""
        return self._requisicao("GET", video_id, {"fields": "status"})

    def publicar(self, mensagem: str = "", link: str | None = None,
                 imagens: list[str] | str | None = None, reel: str | None = None,
                 quando: datetime | None = None) -> dict:
        """Publica agora, ou agenda no Facebook se `quando` for informado.

        - só texto/link            -> post normal
        - uma imagem               -> post de foto
        - várias imagens           -> um post com todas as fotos
        - reel (vídeo vertical)    -> Reel
        """
        if isinstance(imagens, str):
            imagens = [imagens]
        imagens = [i for i in (imagens or []) if i]
        if not (mensagem or link or imagens or reel):
            raise ErroFacebook("O post precisa de texto, link, imagem ou reel.")
        if reel and imagens:
            raise ErroFacebook("Um Reel não pode ter imagens junto: faça dois posts.")

        # Valida o horário antes de enviar qualquer arquivo.
        agendado = validar_horario(quando) if quando is not None else None

        if (imagens or reel) and link:
            # Fotos e Reels não aceitam o campo link: ele vai no fim do texto.
            mensagem = f"{mensagem}\n\n{link}".strip()

        if reel:
            return self._publicar_reel(reel, mensagem, agendado)
        if len(imagens) == 1:
            return self._enviar_foto(imagens[0], mensagem, agendado, publicada=True)
        if imagens:
            return self._publicar_varias_fotos(imagens, mensagem, agendado)

        extra = {"published": "false", "scheduled_publish_time": agendado} if agendado else {}
        return self._requisicao("POST", f"{self.page_id}/feed",
                                {"message": mensagem or None, "link": link, **extra})

    # ------------------------------------------------------------- fotos

    def _enviar_foto(self, imagem: str, legenda: str, agendado: int | None,
                     publicada: bool) -> dict:
        campos: dict = {"caption": legenda or None}
        if not publicada:
            # Foto "solta", que depois é anexada a um post com várias fotos.
            campos["published"] = "false"
            if agendado:
                campos["temporary"] = "true"
        elif agendado:
            campos.update(published="false", scheduled_publish_time=agendado)

        if _e_url(imagem):
            campos["url"] = imagem
            return self._requisicao("POST", f"{self.page_id}/photos", campos)
        return self._requisicao("POST", f"{self.page_id}/photos", campos,
                                arquivo=_arquivo_local(imagem, "Imagem"))

    def _publicar_varias_fotos(self, imagens: list[str], mensagem: str,
                               agendado: int | None) -> dict:
        campos: dict = {"message": mensagem or None}
        for i, imagem in enumerate(imagens):
            print(f"  enviando foto {i + 1}/{len(imagens)}...", file=sys.stderr)
            foto = self._enviar_foto(imagem, "", agendado, publicada=False)
            campos[f"attached_media[{i}]"] = json.dumps({"media_fbid": foto["id"]})
        if agendado:
            campos.update(published="false", scheduled_publish_time=agendado)
        return self._requisicao("POST", f"{self.page_id}/feed", campos)

    # ------------------------------------------------------------- reels

    def _publicar_reel(self, video: str, descricao: str, agendado: int | None) -> dict:
        # 1) Pede ao Facebook um espaço para o vídeo.
        inicio = self._requisicao("POST", f"{self.page_id}/video_reels",
                                  {"upload_phase": "start"})
        video_id = inicio["video_id"]
        url_envio = inicio.get("upload_url") or (
            f"https://rupload.facebook.com/video-upload/{self.versao}/{video_id}")

        # 2) Envia o vídeo (arquivo local ou URL pública).
        cabecalhos = {"Authorization": f"OAuth {self.token}"}
        if _e_url(video):
            cabecalhos["file_url"] = video
            corpo = b""
        else:
            caminho = _arquivo_local(video, "Vídeo")
            corpo = caminho.read_bytes()
            cabecalhos.update(offset="0", file_size=str(len(corpo)),
                              **{"Content-Type": "application/octet-stream"})
        print(f"  enviando vídeo ({len(corpo) / 1e6:.1f} MB)..." if corpo
              else "  enviando vídeo pela URL...", file=sys.stderr)
        envio = self._enviar(urllib.request.Request(url_envio, data=corpo, method="POST",
                                                    headers=cabecalhos), timeout=900)
        if not envio.get("success", True):
            raise ErroFacebook(f"O Facebook não aceitou o vídeo: {envio}")

        # 3) Publica ou agenda.
        campos: dict = {"upload_phase": "finish", "video_id": video_id,
                        "description": descricao or None}
        if agendado:
            campos.update(video_state="SCHEDULED", scheduled_publish_time=agendado)
        else:
            campos["video_state"] = "PUBLISHED"
        fim = self._requisicao("POST", f"{self.page_id}/video_reels", campos)
        if not fim.get("success", True):
            raise ErroFacebook(f"O Facebook não finalizou o Reel: {fim}")
        return {"id": video_id, **fim}


# ---------------------------------------------------------------- utilidades

def _multipart(campos: dict, nome_arquivo: str, arquivo: Path) -> tuple[bytes, str]:
    fronteira = uuid.uuid4().hex
    partes: list[bytes] = []
    for chave, valor in campos.items():
        partes.append(
            f'--{fronteira}\r\nContent-Disposition: form-data; name="{chave}"\r\n\r\n'
            f"{valor}\r\n".encode("utf-8")
        )
    tipo = mimetypes.guess_type(arquivo.name)[0] or "application/octet-stream"
    partes.append(
        f'--{fronteira}\r\nContent-Disposition: form-data; name="{nome_arquivo}"; '
        f'filename="{arquivo.name}"\r\nContent-Type: {tipo}\r\n\r\n'.encode("utf-8")
    )
    partes.append(arquivo.read_bytes())
    partes.append(f"\r\n--{fronteira}--\r\n".encode("utf-8"))
    return b"".join(partes), f"multipart/form-data; boundary={fronteira}"


def _mensagem_de_erro(e: urllib.error.HTTPError) -> str:
    try:
        dados = json.loads(e.read().decode("utf-8"))
        erro = dados.get("error", dados.get("debug_info", {}))
    except (ValueError, AttributeError):
        return f"Erro HTTP {e.code} do Facebook."
    msg = erro.get("message", f"Erro HTTP {e.code}")
    codigo = erro.get("code")
    if codigo == 190:
        msg += " (token inválido ou expirado: gere um novo token de Página)"
    elif codigo in (10, 200):
        msg += (" (permissão faltando: o token precisa de pages_manage_posts "
                "e pages_read_engagement)")
    return f"Facebook recusou ({codigo}): {msg}"


def ler_horario(texto: str) -> datetime:
    """Aceita ISO 8601, ex.: '2026-12-24T20:00' ou '2026-12-24T20:00-03:00'.

    Sem fuso explícito, usa o fuso local da máquina.
    """
    try:
        dt = datetime.fromisoformat(texto.strip().replace(" ", "T", 1))
    except ValueError:
        raise ErroFacebook(
            f"Horário inválido: {texto!r}. Use o formato 2026-12-24T20:00"
        ) from None
    if dt.tzinfo is None:
        dt = dt.astimezone()  # interpreta como horário local
    return dt


def validar_horario(quando: datetime, agora: float | None = None) -> int:
    ts = int(quando.timestamp())
    diferenca = ts - (time.time() if agora is None else agora)
    if diferenca < AGENDAMENTO_MINIMO_S:
        raise ErroFacebook(
            f"{quando.isoformat()} está a menos de 10 minutos no futuro; "
            "o Facebook não aceita agendar assim."
        )
    if diferenca > AGENDAMENTO_MAXIMO_S:
        raise ErroFacebook(
            f"{quando.isoformat()} está a mais de 30 dias; o Facebook não aceita."
        )
    return ts


def _id_do_post(resp: dict) -> str:
    return resp.get("post_id") or resp.get("id") or "?"


# ---------------------------------------------------------------- fila de posts

def _imagens_do_post(post: dict) -> list[str]:
    imagens = post.get("imagens") or []
    if isinstance(imagens, str):
        imagens = [imagens]
    if post.get("imagem"):
        imagens = [post["imagem"], *imagens]
    return imagens


def agendar_arquivo(cliente: ClienteFacebook | None, arquivo: Path,
                    simular: bool = False) -> int:
    """Agenda no Facebook todos os posts do arquivo JSON que ainda não foram enviados.

    Cada post enviado ganha o campo "id_facebook" no próprio arquivo, então rodar o
    comando de novo não duplica nada. Devolve o número de erros.
    """
    posts = json.loads(arquivo.read_text(encoding="utf-8"))
    if not isinstance(posts, list):
        raise ErroFacebook(f"{arquivo} deve conter uma lista de posts.")

    erros = 0
    for i, post in enumerate(posts, 1):
        rotulo = f"[{i}/{len(posts)}]"
        if post.get("id_facebook"):
            print(f"{rotulo} já enviado ({post['id_facebook']}), pulando.")
            continue
        try:
            quando = ler_horario(post["quando"]) if post.get("quando") else None
            if quando is not None:
                validar_horario(quando)
            imagens = _imagens_do_post(post)
            tipo = ("reel" if post.get("reel") else
                    f"{len(imagens)} fotos" if len(imagens) > 1 else
                    "foto" if imagens else "texto")
            resumo = (post.get("mensagem") or post.get("link") or post.get("reel")
                      or (imagens[0] if imagens else ""))[:50]
            acao = f"agendar para {quando:%d/%m/%Y %H:%M}" if quando else "publicar agora"
            if simular:
                print(f"{rotulo} (simulação) {acao} [{tipo}]: {resumo!r}")
                continue
            assert cliente is not None
            resp = cliente.publicar(post.get("mensagem", ""), post.get("link"),
                                    imagens, post.get("reel"), quando)
            post["id_facebook"] = _id_do_post(resp)
            print(f"{rotulo} ok, {acao} [{tipo}]: {resumo!r} -> {post['id_facebook']}")
            # Salva a cada post para não perder o progresso se algo falhar depois.
            arquivo.write_text(json.dumps(posts, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        except (ErroFacebook, KeyError) as e:
            erros += 1
            print(f"{rotulo} ERRO: {e}", file=sys.stderr)
    return erros


# ---------------------------------------------------------------- linha de comando

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Bot de postagem para Página do Facebook.")
    sub = p.add_subparsers(dest="comando", required=True)

    sub.add_parser("verificar", help="testa o token e mostra o nome da Página")

    pub = sub.add_parser("publicar", help="publica (ou agenda) um post, foto ou Reel")
    pub.add_argument("mensagem", nargs="?", default="", help="texto ou legenda")
    pub.add_argument("--link")
    pub.add_argument("--imagem", action="append", metavar="ARQ_OU_URL",
                     help="imagem (arquivo ou URL); repita para postar várias juntas")
    pub.add_argument("--reel", metavar="VIDEO", help="vídeo vertical (arquivo ou URL)")
    pub.add_argument("--quando", help="agendar, ex.: 2026-12-24T20:00")

    ag = sub.add_parser("agendar", help="agenda todos os posts de um arquivo JSON")
    ag.add_argument("arquivo", type=Path)
    ag.add_argument("--simular", action="store_true",
                    help="mostra o que seria feito, sem enviar nada")

    st = sub.add_parser("status", help="mostra a situação de um Reel enviado")
    st.add_argument("video_id")

    args = p.parse_args(argv)
    try:
        if args.comando == "agendar":
            cliente = None if args.simular else ClienteFacebook.do_ambiente()
            return 1 if agendar_arquivo(cliente, args.arquivo, args.simular) else 0

        cliente = ClienteFacebook.do_ambiente()
        if args.comando == "verificar":
            info = cliente.verificar()
            print(f"Conectado à Página: {info.get('name')} (id {info.get('id')})")
        elif args.comando == "status":
            print(json.dumps(cliente.status_video(args.video_id).get("status", {}),
                             ensure_ascii=False, indent=2))
        else:
            quando = ler_horario(args.quando) if args.quando else None
            resp = cliente.publicar(args.mensagem, args.link, args.imagem,
                                    args.reel, quando)
            estado = "Agendado" if quando else "Publicado"
            print(f"{estado}! id: {_id_do_post(resp)}")
            if args.reel:
                print("O Facebook ainda processa o vídeo por alguns minutos. "
                      f"Acompanhe com: python3 fb_bot.py status {resp['id']}")
        return 0
    except ErroFacebook as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
