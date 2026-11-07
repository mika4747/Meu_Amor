#!/usr/bin/env python3
"""Bot de postagem para Páginas do Facebook (Graph API).

Uso:
    python fb_bot.py publicar "Texto do post" [--link URL] [--imagem CAMINHO_OU_URL]
    python fb_bot.py agendar posts.json [--simular]
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
from datetime import datetime, timezone
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


class ClienteFacebook:
    def __init__(self, page_id: str, token: str, versao: str = VERSAO_PADRAO):
        if not page_id or not token:
            raise ErroFacebook(
                "Defina FB_PAGE_ID e FB_PAGE_ACCESS_TOKEN (veja facebook_bot/README.md)."
            )
        self.page_id = page_id
        self.token = token
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

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ErroFacebook(_mensagem_de_erro(e)) from None
        except urllib.error.URLError as e:
            raise ErroFacebook(f"Falha de conexão com o Facebook: {e.reason}") from None

    # ------------------------------------------------------------- ações

    def verificar(self) -> dict:
        """Confirma que o token funciona e devolve o nome da Página."""
        return self._requisicao("GET", self.page_id, {"fields": "id,name"})

    def publicar(self, mensagem: str = "", link: str | None = None,
                 imagem: str | None = None, quando: datetime | None = None) -> dict:
        """Publica agora, ou agenda no Facebook se `quando` for informado."""
        if not (mensagem or link or imagem):
            raise ErroFacebook("O post precisa de texto, link ou imagem.")

        extra: dict = {}
        if quando is not None:
            extra = {"published": "false",
                     "scheduled_publish_time": validar_horario(quando)}

        if imagem:
            if link:
                # A Graph API não aceita link e foto no mesmo post: põe o link no texto.
                mensagem = f"{mensagem}\n\n{link}".strip()
            campos = {"caption": mensagem or None, **extra}
            if imagem.startswith(("http://", "https://")):
                campos["url"] = imagem
                return self._requisicao("POST", f"{self.page_id}/photos", campos)
            caminho = Path(imagem).expanduser()
            if not caminho.is_file():
                raise ErroFacebook(f"Imagem não encontrada: {imagem}")
            return self._requisicao("POST", f"{self.page_id}/photos", campos, arquivo=caminho)

        campos = {"message": mensagem or None, "link": link, **extra}
        return self._requisicao("POST", f"{self.page_id}/feed", campos)


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
        erro = json.loads(e.read().decode("utf-8")).get("error", {})
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


# ---------------------------------------------------------------- fila de posts

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
            resumo = (post.get("mensagem") or post.get("link") or post.get("imagem") or "")[:50]
            acao = f"agendar para {quando:%d/%m/%Y %H:%M}" if quando else "publicar agora"
            if simular:
                print(f"{rotulo} (simulação) {acao}: {resumo!r}")
                continue
            assert cliente is not None
            resp = cliente.publicar(post.get("mensagem", ""), post.get("link"),
                                    post.get("imagem"), quando)
            post["id_facebook"] = resp.get("post_id") or resp.get("id")
            print(f"{rotulo} ok, {acao}: {resumo!r} -> {post['id_facebook']}")
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

    pub = sub.add_parser("publicar", help="publica (ou agenda) um post")
    pub.add_argument("mensagem", nargs="?", default="")
    pub.add_argument("--link")
    pub.add_argument("--imagem", help="caminho de arquivo local ou URL pública")
    pub.add_argument("--quando", help="agendar, ex.: 2026-12-24T20:00")

    ag = sub.add_parser("agendar", help="agenda todos os posts de um arquivo JSON")
    ag.add_argument("arquivo", type=Path)
    ag.add_argument("--simular", action="store_true",
                    help="mostra o que seria feito, sem enviar nada")

    args = p.parse_args(argv)
    try:
        if args.comando == "agendar":
            cliente = None if args.simular else ClienteFacebook.do_ambiente()
            return 1 if agendar_arquivo(cliente, args.arquivo, args.simular) else 0

        cliente = ClienteFacebook.do_ambiente()
        if args.comando == "verificar":
            info = cliente.verificar()
            print(f"Conectado à Página: {info.get('name')} (id {info.get('id')})")
        else:
            quando = ler_horario(args.quando) if args.quando else None
            resp = cliente.publicar(args.mensagem, args.link, args.imagem, quando)
            estado = "Agendado" if quando else "Publicado"
            print(f"{estado}! id: {resp.get('post_id') or resp.get('id')}")
        return 0
    except ErroFacebook as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
