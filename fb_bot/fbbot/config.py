"""Carrega a configuração do bot a partir de variáveis de ambiente / arquivo .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def load_dotenv(path: str | os.PathLike = ".env") -> None:
    """Leitor simples de .env (sem dependências). Não sobrescreve variáveis já definidas."""
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass
class Config:
    user_token: str = ""
    app_id: str = ""
    app_secret: str = ""
    api_version: str = "v23.0"
    default_page_id: str = ""
    queue_dir: Path = field(default_factory=lambda: Path("fila"))
    queue_interval_minutes: int = 240

    @classmethod
    def from_env(cls, env_file: str | os.PathLike = ".env") -> "Config":
        load_dotenv(env_file)
        return cls(
            user_token=os.getenv("FB_USER_TOKEN", ""),
            app_id=os.getenv("FB_APP_ID", ""),
            app_secret=os.getenv("FB_APP_SECRET", ""),
            api_version=os.getenv("FB_API_VERSION", "v23.0"),
            default_page_id=os.getenv("FB_PAGE_ID", ""),
            queue_dir=Path(os.getenv("FB_QUEUE_DIR", "fila")),
            queue_interval_minutes=int(os.getenv("FB_QUEUE_INTERVAL_MINUTES", "240")),
        )
