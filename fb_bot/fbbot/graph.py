"""Cliente mínimo para a Graph API do Facebook (Páginas + Reels)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

GRAPH_HOST = "https://graph.facebook.com"
RUPLOAD_HOST = "https://rupload.facebook.com"


class GraphError(RuntimeError):
    """Erro retornado pela Graph API."""

    def __init__(self, message: str, payload: Any = None, status: int | None = None):
        super().__init__(message)
        self.payload = payload
        self.status = status


@dataclass
class Page:
    id: str
    name: str
    access_token: str
    category: str = ""


class GraphClient:
    def __init__(self, token: str, api_version: str = "v23.0", session: requests.Session | None = None,
                 timeout: int = 60):
        if not token:
            raise ValueError("Token de acesso ausente. Defina FB_USER_TOKEN no arquivo .env")
        self.token = token
        self.api_version = api_version
        self.session = session or requests.Session()
        self.timeout = timeout

    # ------------------------------------------------------------------ helpers
    def _url(self, path: str) -> str:
        return f"{GRAPH_HOST}/{self.api_version}/{path.lstrip('/')}"

    @staticmethod
    def _handle(resp: requests.Response) -> Any:
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text}
        if resp.status_code >= 400 or (isinstance(data, dict) and "error" in data):
            err = data.get("error", {}) if isinstance(data, dict) else {}
            msg = err.get("message") or f"HTTP {resp.status_code}"
            raise GraphError(f"Graph API: {msg}", payload=data, status=resp.status_code)
        return data

    def get(self, path: str, token: str | None = None, **params: Any) -> Any:
        params["access_token"] = token or self.token
        return self._handle(self.session.get(self._url(path), params=params, timeout=self.timeout))

    def post(self, path: str, token: str | None = None, files: Any = None, **params: Any) -> Any:
        params["access_token"] = token or self.token
        return self._handle(self.session.post(self._url(path), data=params, files=files, timeout=self.timeout))

    def delete(self, path: str, token: str | None = None) -> Any:
        return self._handle(self.session.delete(self._url(path), params={"access_token": token or self.token},
                                                timeout=self.timeout))

    # ------------------------------------------------------------------ tokens
    def exchange_long_lived_token(self, app_id: str, app_secret: str) -> dict:
        """Troca o token de usuário de curta duração por um de ~60 dias."""
        return self.get("oauth/access_token", grant_type="fb_exchange_token", client_id=app_id,
                        client_secret=app_secret, fb_exchange_token=self.token)

    # ------------------------------------------------------------------ páginas
    def list_pages(self) -> list[Page]:
        pages: list[Page] = []
        data = self.get("me/accounts", fields="id,name,access_token,category", limit=100)
        while True:
            for p in data.get("data", []):
                pages.append(Page(p["id"], p.get("name", ""), p.get("access_token", ""), p.get("category", "")))
            nxt = data.get("paging", {}).get("next")
            if not nxt:
                break
            data = self._handle(self.session.get(nxt, timeout=self.timeout))
        return pages

    def page(self, page_id: str) -> Page:
        for p in self.list_pages():
            if p.id == page_id:
                return p
        raise GraphError(f"Página {page_id} não encontrada entre as páginas que você administra.")

    # ------------------------------------------------------------------ posts
    def post_text(self, page: Page, message: str, link: str | None = None,
                  scheduled_time: int | None = None) -> dict:
        params: dict[str, Any] = {"message": message}
        if link:
            params["link"] = link
        if scheduled_time:
            params.update(published="false", scheduled_publish_time=scheduled_time)
        return self.post(f"{page.id}/feed", token=page.access_token, **params)

    def post_photo(self, page: Page, source: str, caption: str = "") -> dict:
        if source.startswith(("http://", "https://")):
            return self.post(f"{page.id}/photos", token=page.access_token, url=source, caption=caption)
        with open(source, "rb") as fh:
            return self.post(f"{page.id}/photos", token=page.access_token, caption=caption,
                             files={"source": (Path(source).name, fh)})

    def list_posts(self, page: Page, limit: int = 10) -> list[dict]:
        data = self.get(f"{page.id}/posts", token=page.access_token,
                        fields="id,message,created_time,permalink_url", limit=limit)
        return data.get("data", [])

    def delete_post(self, page: Page, post_id: str) -> dict:
        return self.delete(post_id, token=page.access_token)

    # ------------------------------------------------------------------ comentários
    def list_comments(self, page: Page, object_id: str, limit: int = 25) -> list[dict]:
        data = self.get(f"{object_id}/comments", token=page.access_token,
                        fields="id,from,message,created_time", limit=limit, order="reverse_chronological")
        return data.get("data", [])

    def reply_comment(self, page: Page, comment_id: str, message: str) -> dict:
        return self.post(f"{comment_id}/comments", token=page.access_token, message=message)

    def hide_comment(self, page: Page, comment_id: str, hidden: bool = True) -> dict:
        return self.post(comment_id, token=page.access_token, is_hidden=str(hidden).lower())

    # ------------------------------------------------------------------ reels
    def publish_reel(self, page: Page, video: str, description: str = "", title: str | None = None,
                     scheduled_time: int | None = None, wait: bool = True,
                     poll_seconds: int = 5, max_wait_seconds: int = 600) -> dict:
        """Publica um Reel em 3 fases: start -> upload -> finish.

        `video` pode ser um caminho local ou uma URL pública (https://...).
        `scheduled_time` é um timestamp Unix (entre 10 min e 29 dias no futuro).
        """
        # 1) start
        start = self.post(f"{page.id}/video_reels", token=page.access_token, upload_phase="start")
        video_id = start["video_id"]

        # 2) upload
        upload_url = start.get("upload_url") or f"{RUPLOAD_HOST}/video-upload/{self.api_version}/{video_id}"
        headers = {"Authorization": f"OAuth {page.access_token}"}
        if video.startswith(("http://", "https://")):
            headers["file_url"] = video
            resp = self.session.post(upload_url, headers=headers, timeout=self.timeout)
        else:
            size = os.path.getsize(video)
            headers.update({"offset": "0", "file_size": str(size)})
            with open(video, "rb") as fh:
                resp = self.session.post(upload_url, headers=headers, data=fh, timeout=max(self.timeout, 600))
        up = self._handle(resp)
        if isinstance(up, dict) and up.get("success") is False:
            raise GraphError("Falha no upload do vídeo", payload=up)

        # 3) finish
        params: dict[str, Any] = {"upload_phase": "finish", "video_id": video_id, "description": description}
        if title:
            params["title"] = title
        if scheduled_time:
            params.update(video_state="SCHEDULED", scheduled_publish_time=scheduled_time)
        else:
            params["video_state"] = "PUBLISHED"
        fin = self.post(f"{page.id}/video_reels", token=page.access_token, **params)

        result = {"video_id": video_id, "finish": fin}
        if wait and not scheduled_time:
            result["status"] = self.wait_reel(page, video_id, poll_seconds, max_wait_seconds)
        return result

    def reel_status(self, page: Page, video_id: str) -> dict:
        return self.get(video_id, token=page.access_token, fields="status,permalink_url")

    def wait_reel(self, page: Page, video_id: str, poll_seconds: int = 5, max_wait_seconds: int = 600) -> dict:
        deadline = time.monotonic() + max_wait_seconds
        while True:
            info = self.reel_status(page, video_id)
            status = info.get("status", {})
            video_status = status.get("video_status")
            if video_status in ("ready", "published") or status.get("publishing_phase", {}).get("status") == "complete":
                return info
            if video_status == "error" or status.get("processing_phase", {}).get("status") == "error":
                raise GraphError("O Facebook rejeitou o vídeo durante o processamento", payload=info)
            if time.monotonic() > deadline:
                return info
            time.sleep(poll_seconds)

    def list_reels(self, page: Page, limit: int = 10) -> list[dict]:
        data = self.get(f"{page.id}/video_reels", token=page.access_token,
                        fields="id,description,created_time,permalink_url", limit=limit)
        return data.get("data", [])
