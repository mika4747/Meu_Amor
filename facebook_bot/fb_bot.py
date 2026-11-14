#!/usr/bin/env python3
"""Bot de postagem para Páginas do Facebook (Graph API): textos, fotos e Reels.

Uso:
    python fb_bot.py publicar "Texto" [--link URL] [--imagem ARQ_OU_URL ...] [--quando DATA]
    python fb_bot.py publicar "Legenda" --reel VIDEO.mp4 [--quando DATA]
    python fb_bot.py agendar posts.json [--calendario calendario.json] [--simular]
    python fb_bot.py status ID_DO_REEL [--pagina PAGINA]
    python fb_bot.py conectar          (conecta todas as suas Páginas)
    python fb_bot.py paginas [--padrao PAGINA]
    python fb_bot.py verificar

    Em publicar: --pagina "Nome" (repita para várias) ou --todas.
    Sem isso, o post sai na Página padrão.

Configuração: o comando "conectar" grava os tokens das Páginas em paginas.json.
Também dá para configurar uma Página só à mão (variáveis de ambiente ou .env):
    FB_PAGE_ID            ID numérico da Página
    FB_PAGE_ACCESS_TOKEN  Token de acesso da Página (não o token de usuário)
    FB_GRAPH_VERSION      Opcional, padrão "v24.0"

Só usa a biblioteca padrão do Python (3.9+).
"""

from __future__ import annotations

import argparse
import getpass
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
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


# ---------------------------------------------------------------- legendas e hashtags

def normalizar_hashtags(*grupos) -> list[str]:
    """Junta hashtags de listas ou textos ("amor, #foto viagem") no formato #palavra."""
    vistas: set[str] = set()
    saida: list[str] = []
    for grupo in grupos:
        if not grupo:
            continue
        itens = grupo.replace(",", " ").split() if isinstance(grupo, str) else grupo
        for item in itens:
            tag = "#" + "".join(str(item).split()).lstrip("#")
            if tag != "#" and tag.lower() not in vistas:
                vistas.add(tag.lower())
                saida.append(tag)
    return saida


def montar_legenda(mensagem: str = "", hashtags: list[str] | None = None,
                   assinatura: str = "") -> str:
    """Texto + assinatura + hashtags (sem repetir hashtags que já estão no texto)."""
    partes = [p.strip() for p in (mensagem, assinatura) if p and p.strip()]
    texto = "\n\n".join(partes)
    ja_no_texto = {palavra.lower().rstrip(".,!?;:") for palavra in texto.split()}
    novas = [h for h in (hashtags or []) if h.lower() not in ja_no_texto]
    if novas:
        texto = f"{texto}\n\n{' '.join(novas)}".strip()
    return texto


# ---------------------------------------------------------------- calendário

DIAS_DA_SEMANA = {"seg": 0, "ter": 1, "qua": 2, "qui": 3, "sex": 4,
                  "sab": 5, "sáb": 5, "dom": 6}


def _ler_fuso(texto: str):
    texto = (texto or "-03:00").strip()
    if texto[:1] in "+-":
        try:
            horas, minutos = texto[1:].split(":")
            delta = timedelta(hours=int(horas), minutes=int(minutos))
        except ValueError:
            raise ErroFacebook(f"Fuso inválido: {texto!r} (use algo como -03:00)") from None
        return timezone(-delta if texto[0] == "-" else delta)
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(texto)
    except Exception:
        raise ErroFacebook(f"Fuso desconhecido: {texto!r} (use algo como -03:00)") from None


def carregar_calendario(caminho: Path) -> dict:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ErroFacebook(f"Calendário não encontrado: {caminho}") from None
    except ValueError as e:
        raise ErroFacebook(f"{caminho} não é um JSON válido: {e}") from None

    horarios = []
    for h in dados.get("horarios") or []:
        try:
            horarios.append(datetime.strptime(h.strip(), "%H:%M").time())
        except (ValueError, AttributeError):
            raise ErroFacebook(f"Horário inválido no calendário: {h!r} (use 09:00)") from None
    if not horarios:
        raise ErroFacebook(f"{caminho}: informe pelo menos um horário em \"horarios\".")

    dias = set()
    for d in dados.get("dias") or list(DIAS_DA_SEMANA):
        chave = str(d).strip().lower()[:3]
        if chave not in DIAS_DA_SEMANA:
            raise ErroFacebook(f"Dia inválido no calendário: {d!r} (use seg, ter, ... dom)")
        dias.add(DIAS_DA_SEMANA[chave])

    return {
        "horarios": sorted(set(horarios)),
        "dias": dias,
        "fuso": _ler_fuso(dados.get("fuso", "-03:00")),
        "hashtags": normalizar_hashtags(dados.get("hashtags")),
        "assinatura": dados.get("assinatura", ""),
    }


def proximos_horarios(calendario: dict, ocupados: set[int],
                      agora: datetime | None = None):
    """Gera, em ordem, os horários livres do calendário que o Facebook aceita."""
    fuso = calendario["fuso"]
    agora = (agora or datetime.now(timezone.utc)).astimezone(fuso)
    inicio = agora + timedelta(seconds=AGENDAMENTO_MINIMO_S + 5 * 60)  # folga de 5 min
    fim = agora + timedelta(seconds=AGENDAMENTO_MAXIMO_S - 60 * 60)
    dia = inicio.date()
    while dia <= fim.date():
        if dia.weekday() in calendario["dias"]:
            for h in calendario["horarios"]:
                dt = datetime.combine(dia, h, tzinfo=fuso)
                if inicio <= dt <= fim and int(dt.timestamp()) not in ocupados:
                    yield dt
        dia += timedelta(days=1)


# ---------------------------------------------------------------- fila de posts

def _imagens_do_post(post: dict) -> list[str]:
    imagens = post.get("imagens") or []
    if isinstance(imagens, str):
        imagens = [imagens]
    if post.get("imagem"):
        imagens = [post["imagem"], *imagens]
    return imagens


def _distribuir_horarios(posts: list[dict], calendario: dict,
                         agora: datetime | None) -> tuple[set[int], int]:
    """Põe "quando" nos posts pendentes que não têm horário.

    Devolve (índices preenchidos agora, quantos ficaram sem vaga).
    """
    ocupados = set()
    for post in posts:
        quando = post.get("quando")
        if quando and quando != "agora":
            try:
                ocupados.add(int(ler_horario(quando).timestamp()))
            except ErroFacebook:
                pass  # o erro aparece ao processar esse post
    livres = proximos_horarios(calendario, ocupados, agora)
    preenchidos, sem_vaga = set(), 0
    for i, post in enumerate(posts):
        if _ja_enviado(post) or post.get("quando"):
            continue
        dt = next(livres, None)
        if dt is None:
            sem_vaga += 1
            continue
        post["quando"] = dt.isoformat(timespec="minutes")
        preenchidos.add(i)
    return preenchidos, sem_vaga


def _ja_enviado(post: dict) -> bool:
    """True se o post já saiu em pelo menos uma Página."""
    return bool(post.get("id_facebook") or post.get("enviados"))


def _salvar(arquivo: Path, posts: list[dict], preenchidos: set[int]) -> None:
    """Grava o arquivo. Horários escolhidos pelo calendário só ficam gravados nos
    posts que foram de fato enviados; os outros ganham um horário novo na próxima vez."""
    copia = []
    for i, post in enumerate(posts):
        if i in preenchidos and not _ja_enviado(post):
            post = {k: v for k, v in post.items() if k != "quando"}
        copia.append(post)
    arquivo.write_text(json.dumps(copia, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")


def agendar_arquivo(conta: "Conta | None", arquivo: Path,
                    simular: bool = False, calendario: dict | None = None,
                    agora: datetime | None = None) -> int:
    """Agenda no Facebook todos os posts do arquivo JSON que ainda não foram enviados.

    Cada post pode dizer em quais Páginas sai (campo "paginas": nome, id, lista ou
    "todas"); sem ele, sai na Página padrão. Com um calendário, posts sem "quando" vão
    para o próximo horário livre e as hashtags/assinatura entram na legenda.
    O bot anota em "enviados" as Páginas onde cada post já saiu, então rodar de novo
    não duplica nada (e, se uma Página falhar, só ela é tentada de novo).
    Devolve o número de erros.
    """
    posts = json.loads(arquivo.read_text(encoding="utf-8"))
    if not isinstance(posts, list):
        raise ErroFacebook(f"{arquivo} deve conter uma lista de posts.")

    preenchidos, sem_vaga = (_distribuir_horarios(posts, calendario, agora)
                             if calendario else (set(), 0))
    hashtags_gerais = calendario["hashtags"] if calendario else []
    assinatura = calendario["assinatura"] if calendario else ""

    erros = 0
    for i, post in enumerate(posts):
        rotulo = f"[{i + 1}/{len(posts)}]"
        if post.get("id_facebook"):  # formato antigo: enviado para a Página única
            print(f"{rotulo} já enviado ({post['id_facebook']}), pulando.")
            continue
        enviados = dict(post.get("enviados") or {})
        try:
            alvos = conta.resolver(post.get("paginas")) if conta else []
        except ErroFacebook as e:
            erros += 1
            print(f"{rotulo} ERRO: {e}", file=sys.stderr)
            continue
        faltam = [p for p in alvos if p["id"] not in enviados]
        if alvos and not faltam:
            print(f"{rotulo} já enviado em {_nomes(alvos)}, pulando.")
            continue
        if calendario and not post.get("quando"):
            print(f"{rotulo} sem horário livre nos próximos 30 dias; fica para depois.")
            continue
        try:
            texto_quando = post.get("quando")
            quando = (ler_horario(texto_quando)
                      if texto_quando and texto_quando != "agora" else None)
            if quando is not None:
                validar_horario(quando)
            imagens = _imagens_do_post(post)
            tipo = ("reel" if post.get("reel") else
                    f"{len(imagens)} fotos" if len(imagens) > 1 else
                    "foto" if imagens else "texto")
            legenda = montar_legenda(
                post.get("mensagem", ""),
                normalizar_hashtags(hashtags_gerais, post.get("hashtags")),
                post.get("assinatura", assinatura),
            )
            resumo = (post.get("mensagem") or post.get("link") or post.get("reel")
                      or (imagens[0] if imagens else ""))[:50]
            acao = f"agendar para {quando:%d/%m/%Y %H:%M}" if quando else "publicar agora"
        except (ErroFacebook, KeyError) as e:
            erros += 1
            print(f"{rotulo} ERRO: {e}", file=sys.stderr)
            continue

        if simular:
            onde = _nomes(faltam) if faltam else (
                ", ".join(_como_lista(post.get("paginas"))) or "Página padrão")
            print(f"{rotulo} (simulação) {acao} [{tipo}] em {onde}: {resumo!r}")
            linhas = legenda.splitlines() or [""]
            print("      legenda: " + linhas[0])
            for linha in linhas[1:]:
                print(f"               {linha}".rstrip())
            continue

        for pagina in faltam:
            try:
                resp = conta.cliente(pagina).publicar(
                    legenda, post.get("link"), imagens, post.get("reel"), quando)
            except ErroFacebook as e:
                erros += 1
                print(f"{rotulo} ERRO em {pagina['nome']}: {e}", file=sys.stderr)
                continue
            enviados[pagina["id"]] = _id_do_post(resp)
            post["enviados"] = enviados
            print(f"{rotulo} ok em {pagina['nome']}, {acao} [{tipo}]: {resumo!r} "
                  f"-> {enviados[pagina['id']]}")
            # Salva a cada envio para não perder o progresso se algo falhar depois.
            _salvar(arquivo, posts, preenchidos)
    if sem_vaga:
        print(f"{sem_vaga} post(s) aguardando vaga: rode o comando de novo nos "
              "próximos dias (o Facebook só agenda até 30 dias à frente).")
    return erros


# ---------------------------------------------------------------- Páginas conectadas

ARQUIVO_PAGINAS = PASTA / "paginas.json"


def _como_lista(selecao) -> list[str]:
    if selecao is None or selecao == "":
        return []
    if isinstance(selecao, str):
        return [s.strip() for s in selecao.split(",") if s.strip()]
    return [str(s).strip() for s in selecao if str(s).strip()]


def _nomes(paginas: list[dict]) -> str:
    return ", ".join(p["nome"] for p in paginas)


def _gravar_privado(caminho: Path, texto: str) -> None:
    caminho.write_text(texto, encoding="utf-8")
    try:
        caminho.chmod(0o600)  # só o seu usuário pode ler os tokens
    except OSError:
        pass


class Conta:
    """As Páginas conectadas ao bot (com o token de cada uma)."""

    def __init__(self, paginas: list[dict], versao: str = VERSAO_PADRAO, fabrica=None):
        self.paginas = paginas
        self.versao = versao
        # fabrica(pagina) -> cliente; os testes trocam por um cliente falso.
        self._fabrica = fabrica or (
            lambda p: ClienteFacebook(p["id"], p["token"], self.versao))

    @classmethod
    def do_ambiente(cls, caminho: Path | None = None) -> "Conta":
        """Lê paginas.json (criado pelo comando conectar) ou, se não existir, a
        Página única do .env (FB_PAGE_ID e FB_PAGE_ACCESS_TOKEN)."""
        carregar_env()
        caminho = caminho or ARQUIVO_PAGINAS
        versao = os.environ.get("FB_GRAPH_VERSION", VERSAO_PADRAO)
        if caminho.exists():
            try:
                paginas = json.loads(caminho.read_text(encoding="utf-8"))
            except ValueError as e:
                raise ErroFacebook(f"{caminho} está corrompido: {e}. "
                                   "Rode 'python3 fb_bot.py conectar' de novo.") from None
            return cls(paginas, versao)
        page_id = os.environ.get("FB_PAGE_ID", "")
        token = os.environ.get("FB_PAGE_ACCESS_TOKEN", "")
        if page_id and token:
            return cls([{"id": page_id, "nome": os.environ.get("FB_PAGE_NAME", page_id),
                         "token": token, "padrao": True}], versao)
        return cls([], versao)

    def salvar(self, caminho: Path | None = None) -> None:
        _gravar_privado(caminho or ARQUIVO_PAGINAS,
                        json.dumps(self.paginas, ensure_ascii=False, indent=2) + "\n")

    def padrao(self) -> dict:
        if not self.paginas:
            raise ErroFacebook("Nenhuma Página conectada. Rode: python3 fb_bot.py conectar")
        return next((p for p in self.paginas if p.get("padrao")), self.paginas[0])

    def definir_padrao(self, selecao: str) -> dict:
        escolhida = self.resolver(selecao)
        if len(escolhida) != 1:
            raise ErroFacebook("Escolha uma Página só para ser a padrão.")
        for p in self.paginas:
            p["padrao"] = p["id"] == escolhida[0]["id"]
        return escolhida[0]

    def resolver(self, selecao=None) -> list[dict]:
        """Nome(s) ou id(s) de Página -> Páginas. Vazio = padrão; "todas" = todas."""
        nomes = _como_lista(selecao)
        if not nomes:
            return [self.padrao()]
        if not self.paginas:
            self.padrao()  # dá o erro de "nenhuma Página conectada"
        if any(n.lower() == "todas" for n in nomes):
            return list(self.paginas)
        escolhidas = []
        for nome in nomes:
            achada = next((p for p in self.paginas
                           if nome == p["id"] or nome.lower() == p["nome"].lower()), None)
            if achada is None:
                raise ErroFacebook(f"Página {nome!r} não está conectada. Conectadas: "
                                   f"{_nomes(self.paginas)}.")
            if achada not in escolhidas:
                escolhidas.append(achada)
        return escolhidas

    def cliente(self, pagina: dict):
        return self._fabrica(pagina)


# ---------------------------------------------------------------- conexão (token)

PERMISSOES_NECESSARIAS = ("pages_show_list", "pages_read_engagement", "pages_manage_posts")


def _get(url: str, campos: dict) -> dict:
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(campos)}")
    return ClienteFacebook._enviar(req)


def salvar_env(valores: dict, caminho: Path = PASTA / ".env") -> None:
    """Atualiza (ou cria) o .env mantendo as outras linhas."""
    linhas = caminho.read_text(encoding="utf-8").splitlines() if caminho.exists() else []
    restantes = dict(valores)
    novas = []
    for linha in linhas:
        chave = linha.split("=", 1)[0].strip()
        if chave in restantes and not linha.lstrip().startswith("#"):
            novas.append(f"{chave}={restantes.pop(chave)}")
        else:
            novas.append(linha)
    novas += [f"{k}={v}" for k, v in restantes.items()]
    _gravar_privado(caminho, "\n".join(novas) + "\n")


def obter_paginas(app_id: str, app_secret: str, token_usuario: str,
                  versao: str = VERSAO_PADRAO) -> list[dict]:
    """Troca um token de usuário (curto) pelos tokens de todas as Páginas que a pessoa
    administra. Esses tokens de Página não expiram.

    Devolve [{"id", "nome", "token", "expira", "faltando"}, ...].
    """
    base = f"https://graph.facebook.com/{versao}"
    # 1) token de usuário curto (~1h) -> token de usuário longo (~60 dias)
    longo = _get(f"{base}/oauth/access_token", {
        "grant_type": "fb_exchange_token", "client_id": app_id,
        "client_secret": app_secret, "fb_exchange_token": token_usuario,
    })["access_token"]

    # 2) a partir do token longo, os tokens de Página não expiram
    dados: list[dict] = []
    url, campos = f"{base}/me/accounts", {
        "fields": "id,name,access_token", "limit": 100, "access_token": longo}
    while url:  # segue a paginação, para quem administra muitas Páginas
        resposta = _get(url, campos)
        dados += resposta.get("data", [])
        url = resposta.get("paging", {}).get("next")
        campos = {}  # o link "next" já traz todos os parâmetros
        if url and "?" in url:
            url, consulta = url.split("?", 1)
            campos = dict(urllib.parse.parse_qsl(consulta))
    if not dados:
        raise ErroFacebook(
            "Nenhuma Página encontrada. Ao gerar o token, autorize as suas Páginas e as "
            "permissões " + ", ".join(PERMISSOES_NECESSARIAS) + "."
        )

    # 3) confere validade e permissões de cada token (só para avisar; não bloqueia)
    paginas = []
    for p in dados:
        pagina = {"id": p["id"], "nome": p["name"], "token": p["access_token"],
                  "expira": None, "faltando": []}
        try:
            info = _get(f"{base}/debug_token", {
                "input_token": p["access_token"],
                "access_token": f"{app_id}|{app_secret}",
            }).get("data", {})
            pagina["expira"] = info.get("expires_at")
            escopos = set(info.get("scopes", []))
            pagina["faltando"] = [x for x in PERMISSOES_NECESSARIAS if x not in escopos]
        except ErroFacebook:
            pass
        paginas.append(pagina)
    return paginas


def _escolher_no_terminal(nomes: list[str], pergunta: str) -> int:
    for i, nome in enumerate(nomes, 1):
        print(f"  {i}) {nome}")
    while True:
        resp = input(pergunta).strip()
        if resp.isdigit() and 1 <= int(resp) <= len(nomes):
            return int(resp) - 1
        print("Opção inválida.")


def comando_conectar(escolher=None) -> int:
    carregar_env()
    print("Conectar o bot às suas Páginas do Facebook (passo a passo no README).\n")
    app_id = os.environ.get("FB_APP_ID") or input("ID do app (App ID): ").strip()
    app_secret = (os.environ.get("FB_APP_SECRET")
                  or getpass.getpass("Chave secreta do app (App Secret; não aparece "
                                     "na tela ao colar): ").strip())
    token = getpass.getpass("Token de acesso do usuário, do Graph API Explorer "
                            "(não aparece na tela ao colar): ").strip()
    if not (app_id and app_secret and token):
        raise ErroFacebook("App ID, App Secret e token são obrigatórios.")

    encontradas = obter_paginas(app_id, app_secret, token,
                                versao=os.environ.get("FB_GRAPH_VERSION", VERSAO_PADRAO))

    # mantém a Página padrão de antes, se ela continuar na lista
    anterior = Conta.do_ambiente()
    padrao_antes = next((p["id"] for p in anterior.paginas if p.get("padrao")), None)
    ids = [p["id"] for p in encontradas]
    if padrao_antes in ids:
        indice = ids.index(padrao_antes)
    elif len(encontradas) == 1:
        indice = 0
    else:
        print(f"\nVocê administra {len(encontradas)} Páginas. Todas ficam conectadas.")
        print("Qual é a Página padrão (usada quando o post não diz em qual Página sai)?")
        indice = (escolher or _escolher_no_terminal)(
            [p["nome"] for p in encontradas], "Número da Página padrão: ")

    conta = Conta([{"id": p["id"], "nome": p["nome"], "token": p["token"],
                    "padrao": i == indice} for i, p in enumerate(encontradas)])
    conta.salvar()

    print(f"\nPronto! {len(encontradas)} Página(s) conectada(s):")
    problemas = 0
    for i, p in enumerate(encontradas):
        marca = "  (padrão)" if i == indice else ""
        print(f"  • {p['nome']} (id {p['id']}){marca}")
        if p["expira"]:
            data = datetime.fromtimestamp(p["expira"]).strftime("%d/%m/%Y")
            print(f"    Atenção: o token expira em {data}. Rode 'conectar' antes disso.")
        if p["faltando"]:
            problemas += 1
            print("    Atenção: faltam as permissões " + ", ".join(p["faltando"]) +
                  ". Gere o token de novo marcando essas permissões.")
    print(f"Tokens salvos em {ARQUIVO_PAGINAS} (não compartilhe esse arquivo).")
    if not any(p["expira"] for p in encontradas) and not problemas:
        print("Os tokens das Páginas não expiram.")
    return 1 if problemas else 0


def comando_paginas(conta: Conta, nova_padrao: str | None) -> int:
    if not conta.paginas:
        raise ErroFacebook("Nenhuma Página conectada. Rode: python3 fb_bot.py conectar")
    if nova_padrao:
        escolhida = conta.definir_padrao(nova_padrao)
        conta.salvar()
        print(f"Página padrão agora é: {escolhida['nome']}")
    padrao = conta.padrao()
    print("Páginas conectadas:")
    for p in conta.paginas:
        print(f"  • {p['nome']} (id {p['id']})" + ("  (padrão)" if p is padrao else ""))
    return 0


# ---------------------------------------------------------------- linha de comando

def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:  # evita erro com emojis em terminais do Windows
            fluxo.reconfigure(errors="replace")
        except AttributeError:
            pass
    p = argparse.ArgumentParser(description="Bot de postagem para Páginas do Facebook.")
    sub = p.add_subparsers(dest="comando", required=True)

    sub.add_parser("conectar", help="conecta o bot às suas Páginas e salva os tokens")
    pg = sub.add_parser("paginas", help="lista as Páginas conectadas")
    pg.add_argument("--padrao", metavar="PAGINA", help="muda a Página padrão")
    sub.add_parser("verificar", help="testa o token de cada Página conectada")

    pub = sub.add_parser("publicar", help="publica (ou agenda) um post, foto ou Reel")
    pub.add_argument("mensagem", nargs="?", default="", help="texto ou legenda")
    pub.add_argument("--link")
    pub.add_argument("--imagem", action="append", metavar="ARQ_OU_URL",
                     help="imagem (arquivo ou URL); repita para postar várias juntas")
    pub.add_argument("--reel", metavar="VIDEO", help="vídeo vertical (arquivo ou URL)")
    pub.add_argument("--hashtags", help='hashtags para a legenda, ex.: "#amor #viagem"')
    pub.add_argument("--quando", help="agendar, ex.: 2026-12-24T20:00")
    pub.add_argument("--pagina", action="append", metavar="PAGINA",
                     help="nome ou id da Página (repita para várias); padrão: a Página padrão")
    pub.add_argument("--todas", action="store_true", help="publica em todas as Páginas")

    ag = sub.add_parser("agendar", help="agenda todos os posts de um arquivo JSON")
    ag.add_argument("arquivo", type=Path)
    ag.add_argument("--calendario", type=Path,
                    help="horários fixos e hashtags (padrão: calendario.json ao lado "
                         "do arquivo de posts, se existir)")
    ag.add_argument("--simular", action="store_true",
                    help="mostra o que seria feito, sem enviar nada")

    st = sub.add_parser("status", help="mostra a situação de um Reel enviado")
    st.add_argument("video_id")
    st.add_argument("--pagina", metavar="PAGINA", help="Página do Reel (padrão: a padrão)")

    args = p.parse_args(argv)
    try:
        if args.comando == "conectar":
            return comando_conectar()
        conta = Conta.do_ambiente()
        if args.comando == "paginas":
            return comando_paginas(conta, args.padrao)
        if args.comando == "agendar":
            caminho_cal = args.calendario
            if caminho_cal is None and (args.arquivo.parent / "calendario.json").exists():
                caminho_cal = args.arquivo.parent / "calendario.json"
            calendario = carregar_calendario(caminho_cal) if caminho_cal else None
            if caminho_cal:
                print(f"Usando o calendário {caminho_cal}")
            if not args.simular:
                conta.padrao()  # erro claro se nenhuma Página estiver conectada
            usar = conta if conta.paginas else None
            erros = agendar_arquivo(usar, args.arquivo, args.simular, calendario)
            return 1 if erros else 0

        if args.comando == "verificar":
            falhas = 0
            for pagina in conta.resolver("todas"):
                try:
                    info = conta.cliente(pagina).verificar()
                    print(f"✅ {info.get('name')} (id {info.get('id')})")
                except ErroFacebook as e:
                    falhas += 1
                    print(f"❌ {pagina['nome']}: {e}", file=sys.stderr)
            return 1 if falhas else 0
        if args.comando == "status":
            pagina = conta.resolver(args.pagina)[0]
            print(json.dumps(conta.cliente(pagina).status_video(args.video_id)
                             .get("status", {}), ensure_ascii=False, indent=2))
            return 0

        # publicar
        alvos = conta.resolver("todas" if args.todas else args.pagina)
        quando = ler_horario(args.quando) if args.quando else None
        legenda = montar_legenda(args.mensagem, normalizar_hashtags(args.hashtags))
        estado = "Agendado" if quando else "Publicado"
        falhas = 0
        for pagina in alvos:
            try:
                resp = conta.cliente(pagina).publicar(legenda, args.link, args.imagem,
                                                      args.reel, quando)
            except ErroFacebook as e:
                falhas += 1
                print(f"❌ {pagina['nome']}: {e}", file=sys.stderr)
                continue
            print(f"✅ {estado} em {pagina['nome']}! id: {_id_do_post(resp)}")
            if args.reel:
                print("   O Facebook ainda processa o vídeo por alguns minutos. Acompanhe "
                      f"com: python3 fb_bot.py status {resp['id']} --pagina \"{pagina['nome']}\"")
        return 1 if falhas else 0
    except ErroFacebook as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
