"""Fila de Reels baseada em pasta.

Coloque em `fila/` arquivos de vídeo (.mp4/.mov). Opcionalmente, um .txt com o mesmo
nome contém a legenda. Ex.:  fila/01_praia.mp4  +  fila/01_praia.txt

Os vídeos são publicados em ordem alfabética. Depois de publicados vão para
`fila/publicados/`; se falharem vão para `fila/erros/` (com um .log explicando).
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path

from .graph import GraphClient, Page

VIDEO_EXT = {".mp4", ".mov", ".m4v"}
log = logging.getLogger("fbbot.queue")


def pending_videos(queue_dir: Path) -> list[Path]:
    if not queue_dir.is_dir():
        return []
    return sorted(p for p in queue_dir.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXT)


def caption_for(video: Path) -> str:
    txt = video.with_suffix(".txt")
    return txt.read_text(encoding="utf-8").strip() if txt.is_file() else ""


def _move(video: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for f in (video, video.with_suffix(".txt")):
        if f.exists():
            shutil.move(str(f), dest_dir / f.name)


def process_one(client: GraphClient, page: Page, queue_dir: Path) -> dict | None:
    """Publica o próximo vídeo da fila. Retorna o resultado ou None se a fila estiver vazia."""
    videos = pending_videos(queue_dir)
    if not videos:
        log.info("Fila vazia.")
        return None
    video = videos[0]
    caption = caption_for(video)
    log.info("Publicando %s na página %s…", video.name, page.name)
    try:
        result = client.publish_reel(page, str(video), description=caption)
    except Exception as exc:  # noqa: BLE001 - registrar qualquer falha e seguir com a fila
        _move(video, queue_dir / "erros")
        (queue_dir / "erros" / f"{video.stem}.log").write_text(
            f"{datetime.now().isoformat()}\n{exc}\n{getattr(exc, 'payload', '')}\n", encoding="utf-8")
        log.error("Falhou: %s", exc)
        return {"video": video.name, "error": str(exc)}
    _move(video, queue_dir / "publicados")
    with (queue_dir / "publicados" / "historico.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"when": datetime.now().isoformat(), "video": video.name, "page": page.id,
                             "result": result}, ensure_ascii=False) + "\n")
    log.info("Publicado! video_id=%s", result.get("video_id"))
    return {"video": video.name, **result}


def run_forever(client: GraphClient, page: Page, queue_dir: Path, interval_minutes: int) -> None:
    log.info("Fila iniciada: 1 Reel a cada %s min (Ctrl+C para parar).", interval_minutes)
    while True:
        process_one(client, page, queue_dir)
        time.sleep(interval_minutes * 60)
