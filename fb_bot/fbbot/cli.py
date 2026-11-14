"""Linha de comando do bot.  Uso:  python -m fbbot <comando> [opções]"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime

from .config import Config
from .graph import GraphClient, GraphError, Page
from .queue import process_one, run_forever


def _parse_when(value: str | None) -> int | None:
    """Converte 'AAAA-MM-DD HH:MM' (horário local) em timestamp Unix."""
    if not value:
        return None
    try:
        return int(datetime.strptime(value, "%Y-%m-%d %H:%M").timestamp())
    except ValueError:
        raise argparse.ArgumentTypeError("Use o formato 'AAAA-MM-DD HH:MM', ex.: '2026-12-24 20:00'")


def _print(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _resolve_page(client: GraphClient, cfg: Config, page_id: str | None) -> Page:
    pid = page_id or cfg.default_page_id
    if not pid:
        pages = client.list_pages()
        if len(pages) == 1:
            return pages[0]
        raise SystemExit("Informe --page <ID> ou defina FB_PAGE_ID no .env (veja: python -m fbbot pages)")
    return client.page(pid)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="fbbot", description="Bot para administrar Páginas do Facebook e postar Reels")
    ap.add_argument("--env", default=".env", help="arquivo de configuração (padrão: .env)")
    ap.add_argument("--page", help="ID da página (padrão: FB_PAGE_ID)")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("pages", help="lista as páginas que você administra")
    sub.add_parser("token", help="troca seu token por um de longa duração (~60 dias)")

    r = sub.add_parser("reel", help="publica um Reel")
    r.add_argument("video", help="caminho do vídeo ou URL pública")
    r.add_argument("-d", "--descricao", default="", help="legenda do Reel")
    r.add_argument("--titulo")
    r.add_argument("--agendar", type=_parse_when, help="'AAAA-MM-DD HH:MM' para agendar")
    r.add_argument("--nao-esperar", action="store_true", help="não esperar o processamento terminar")

    sub.add_parser("reels", help="lista os últimos Reels da página")

    s = sub.add_parser("status", help="status de processamento de um Reel")
    s.add_argument("video_id")

    p = sub.add_parser("post", help="publica um post de texto/link")
    p.add_argument("mensagem")
    p.add_argument("--link")
    p.add_argument("--agendar", type=_parse_when)

    f = sub.add_parser("foto", help="publica uma foto")
    f.add_argument("imagem", help="caminho ou URL")
    f.add_argument("-l", "--legenda", default="")

    sub.add_parser("posts", help="lista os últimos posts")

    d = sub.add_parser("apagar", help="apaga um post")
    d.add_argument("post_id")

    c = sub.add_parser("comentarios", help="lista comentários de um post/reel")
    c.add_argument("objeto_id")

    rc = sub.add_parser("responder", help="responde um comentário")
    rc.add_argument("comentario_id")
    rc.add_argument("mensagem")

    h = sub.add_parser("ocultar", help="oculta um comentário")
    h.add_argument("comentario_id")

    q = sub.add_parser("fila", help="publica Reels da pasta de fila")
    q.add_argument("--uma-vez", action="store_true", help="publica só o próximo e sai (bom para cron)")
    q.add_argument("--intervalo", type=int, help="minutos entre publicações")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    cfg = Config.from_env(args.env)
    try:
        client = GraphClient(cfg.user_token, cfg.api_version)

        if args.cmd == "pages":
            for p in client.list_pages():
                print(f"{p.id}\t{p.name}\t({p.category})")
            return 0
        if args.cmd == "token":
            if not (cfg.app_id and cfg.app_secret):
                raise SystemExit("Defina FB_APP_ID e FB_APP_SECRET no .env")
            res = client.exchange_long_lived_token(cfg.app_id, cfg.app_secret)
            print("Novo token (cole em FB_USER_TOKEN no .env):\n" + res["access_token"])
            return 0

        page = _resolve_page(client, cfg, args.page)

        if args.cmd == "reel":
            _print(client.publish_reel(page, args.video, args.descricao, args.titulo, args.agendar,
                                       wait=not args.nao_esperar))
        elif args.cmd == "reels":
            _print(client.list_reels(page))
        elif args.cmd == "status":
            _print(client.reel_status(page, args.video_id))
        elif args.cmd == "post":
            _print(client.post_text(page, args.mensagem, args.link, args.agendar))
        elif args.cmd == "foto":
            _print(client.post_photo(page, args.imagem, args.legenda))
        elif args.cmd == "posts":
            _print(client.list_posts(page))
        elif args.cmd == "apagar":
            _print(client.delete_post(page, args.post_id))
        elif args.cmd == "comentarios":
            _print(client.list_comments(page, args.objeto_id))
        elif args.cmd == "responder":
            _print(client.reply_comment(page, args.comentario_id, args.mensagem))
        elif args.cmd == "ocultar":
            _print(client.hide_comment(page, args.comentario_id))
        elif args.cmd == "fila":
            if args.uma_vez:
                _print(process_one(client, page, cfg.queue_dir))
            else:
                run_forever(client, page, cfg.queue_dir, args.intervalo or cfg.queue_interval_minutes)
        return 0
    except GraphError as e:
        print(f"ERRO: {e}", file=sys.stderr)
        if args.verbose and e.payload:
            _print(e.payload)
        return 1
    except (ValueError, FileNotFoundError) as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
