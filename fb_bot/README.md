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
| `painel` | abre o painel web para usar pelo celular |
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

## 📱 Usar pelo celular (painel web)

```bash
python -m fbbot painel
```

Depois abra **http://localhost:8000** no navegador. No painel você escolhe o vídeo da galeria (ou grava na
hora), escreve a legenda, agenda se quiser e toca em **Publicar Reel**. Também dá para fazer posts de
texto e acompanhar o status dos últimos Reels.

### Android: instalação automática (Termux)

1. Instale o **Termux** pelo **F-Droid** (a versão da Play Store está desatualizada). Se quiser
   atalhos na tela inicial, instale também o **Termux:Widget**.
2. Abra o Termux e cole:
   ```bash
   pkg install -y git && git clone -b ccr-c6110b95-txh3lf https://github.com/mika4747/Meu_Amor && bash Meu_Amor/fb_bot/termux/instalar.sh
   ```
   O instalador pede o token, o App ID e o App Secret, gera o token de 60 dias e pergunta qual página
   usar como padrão.

Depois disso, há três formas de usar:

- **Compartilhar da Galeria:** abra o vídeo, toque em **Compartilhar → Termux** (escolha
  *Edit*/*Abrir*), escreva a legenda e escolha entre publicar agora, agendar ou colocar na fila.
- **Painel:** toque no atalho **Painel do Bot** do widget, ou rode `python -m fbbot painel` dentro de
  `Meu_Amor/fb_bot`. O navegador abre sozinho em `http://localhost:8000`.
- **Fila automática:** use o atalho **Fila de Reels**. Ele publica um vídeo da fila a cada X minutos
  enquanto o Termux estiver aberto. Desative a otimização de bateria do Termux para que o Android não o
  feche.

Para atualizar o bot depois: `cd ~/Meu_Amor && git pull`.

### iPhone (ou acessar de qualquer lugar)

O iPhone não consegue rodar servidores em segundo plano. Nesse caso, rode o painel num computador ou
num servidor e acesse pelo navegador do celular:

```bash
# no .env: PANEL_PASSWORD=uma-senha-forte
python -m fbbot painel --host 0.0.0.0
```

- **Na mesma rede Wi-Fi:** abra `http://IP-DO-COMPUTADOR:8000` no celular.
- **Fora de casa:** hospede num servidor (Render, Railway, uma VPS etc.) e configure as variáveis do
  `.env` no painel da hospedagem. Use sempre **HTTPS** e uma senha forte.

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
