# fbbot: bot para Páginas do Facebook e Reels

Automação usando a **Graph API oficial do Facebook**. Não faz login simulado no navegador,
então não coloca sua conta em risco de bloqueio.

## O que ele faz

| Comando | Função |
|---|---|
| `pages` | lista as páginas que você administra (com os IDs) |
| `reel VIDEO -d "legenda"` | publica um Reel (arquivo local ou URL), com opção de `--agendar` |
| `reels` / `status ID` | lista Reels / mostra o processamento de um Reel |
| `post "texto" [--link] [--agendar]` | post de texto ou link |
| `foto IMAGEM -l "legenda"` | publica uma foto |
| `posts` / `apagar ID` | lista / apaga posts |
| `comentarios ID` / `responder ID "msg"` / `ocultar ID` | modera comentários |
| `fila` | publica automaticamente os vídeos da pasta `fila/` em intervalos |
| `token` | gera um token de longa duração (~60 dias) |

## 1. Configuração (uma vez só)

1. Acesse <https://developers.facebook.com/apps> e crie um app do tipo **Business**.
2. Abra o **Graph API Explorer** (<https://developers.facebook.com/tools/explorer>), escolha seu app e
   clique em **Generate Access Token** com estas permissões:
   - `pages_show_list`
   - `pages_read_engagement`
   - `pages_manage_posts`
   - `pages_manage_engagement` (só se for responder ou ocultar comentários)
3. Copie `.env.example` para `.env` e preencha `FB_USER_TOKEN`, `FB_APP_ID` e `FB_APP_SECRET`
   (o App ID e o App Secret ficam em *Configurações do app → Básico*).
4. Instale e teste:

```bash
cd fb_bot
pip install -r requirements.txt
python -m fbbot token     # troca pelo token de 60 dias; cole o resultado em FB_USER_TOKEN
python -m fbbot pages     # pegue o ID da página e coloque em FB_PAGE_ID
```

> Para usar só nas suas próprias páginas, o app pode ficar em **modo Desenvolvimento**, sem precisar de
> revisão do Facebook, desde que você seja administrador do app e das páginas.

## 2. Postar Reels

```bash
python -m fbbot reel meu_video.mp4 -d "Nosso momento ❤️ #amor"
python -m fbbot reel https://site.com/video.mp4 -d "Via URL"
python -m fbbot reel video.mp4 -d "Natal!" --agendar "2026-12-24 20:00"
python -m fbbot --page 1234567890 reel video.mp4     # outra página
```

**Requisitos do Facebook para Reels:** vertical 9:16, mínimo de 540x960 (ideal 1080x1920),
entre 3 e 90 segundos, .mp4 ou .mov, 24 a 60 fps. Agendamentos devem ficar entre 10 minutos e
29 dias no futuro.

## 3. Fila automática

Coloque os vídeos em `fila/`. Se quiser legenda, crie um `.txt` com o mesmo nome:

```
fila/
  01_praia.mp4
  01_praia.txt      <- legenda do 01_praia
  02_jantar.mp4
```

```bash
python -m fbbot fila                  # roda sem parar: 1 Reel a cada 240 min (ajuste no .env)
python -m fbbot fila --intervalo 60   # 1 por hora
python -m fbbot fila --uma-vez        # publica só o próximo e sai
```

Os vídeos publicados vão para `fila/publicados/` e ficam registrados em `historico.jsonl`.
Os que falharem vão para `fila/erros/`, junto com um `.log` explicando o motivo.

**Exemplo com cron (Linux/Mac)**, para publicar às 12h e às 19h todos os dias:

```
0 12,19 * * * cd /caminho/fb_bot && python3 -m fbbot fila --uma-vez >> bot.log 2>&1
```

No Windows, use o **Agendador de Tarefas** com o mesmo comando.

## Testes

```bash
python -m unittest discover -s tests
```

## Segurança

- Nunca envie o `.env` para o GitHub. Ele já está no `.gitignore`.
- Se o token vazar, invalide-o trocando o App Secret no painel do app.
