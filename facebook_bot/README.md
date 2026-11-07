# Bot de postagem para o Facebook

Publica e agenda **fotos**, **Reels** e posts de texto/link numa **Página do Facebook**
usando a Graph API oficial. Só usa a biblioteca padrão do Python 3.9+ (sem `pip install`).

> ⚠️ A API do Facebook só permite postar em **Páginas**. Perfis pessoais não aceitam
> postagem automática, e a postagem em Grupos pela API foi desativada pela Meta em 2024.

## 1. Pegar o ID e o token da Página

1. Acesse <https://developers.facebook.com/apps>, clique em **Criar app** e escolha um
   caso de uso que inclua **gerenciar Páginas** (tipo *Business* / *Empresa*).
2. Abra o **Graph API Explorer** (<https://developers.facebook.com/tools/explorer>),
   selecione seu app e adicione as permissões:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`.
3. Clique em **Generate Access Token** e autorize a sua Página.
4. No campo **User or Page**, escolha a sua Página: o token mostrado agora é o
   **token da Página**. Rode a consulta `me?fields=id,name` para ver o **ID da Página**.
5. O token do Explorer expira em ~1 hora. Para um token que não expira:
   - troque-o por um token de usuário de longa duração na
     [Ferramenta de Depuração de Token](https://developers.facebook.com/tools/debug/accesstoken/)
     (botão *Extend Access Token*);
   - no Explorer, com esse token longo, consulte `me/accounts`: o `access_token` da sua
     Página que aparece ali não expira.

## 2. Configurar

```bash
cd facebook_bot
cp .env.exemplo .env      # depois edite o .env com o ID e o token
python3 fb_bot.py verificar
# Conectado à Página: Minha Página (id 1234...)
```

O arquivo `.env` está no `.gitignore`: **nunca** faça commit do token.
Em vez do `.env`, também dá para usar as variáveis de ambiente `FB_PAGE_ID` e
`FB_PAGE_ACCESS_TOKEN`.

## 3. Usar

**Publicar agora:**

```bash
python3 fb_bot.py publicar "Olá, mundo!"
python3 fb_bot.py publicar "Veja isso" --link https://example.com
python3 fb_bot.py publicar "Foto nova 📸" --imagem fotos/praia.jpg
python3 fb_bot.py publicar "Da internet" --imagem https://site.com/imagem.jpg
```

**Várias fotos num mesmo post** (repita `--imagem`):

```bash
python3 fb_bot.py publicar "Nosso fim de semana 💛" --imagem f1.jpg --imagem f2.jpg --imagem f3.jpg
```

**Reels:**

```bash
python3 fb_bot.py publicar "Bastidores 🎬 #reels" --reel videos/bastidores.mp4
python3 fb_bot.py publicar "Da internet" --reel https://site.com/video.mp4
```

Depois de enviar, o Facebook leva alguns minutos processando o vídeo. O bot mostra o
ID do Reel; para acompanhar:

```bash
python3 fb_bot.py status ID_DO_REEL
```

O vídeo do Reel precisa seguir as regras do Facebook:

| Requisito   | Valor                                                  |
|-------------|--------------------------------------------------------|
| Formato     | `.mp4` (H.264 + áudio AAC)                             |
| Proporção   | vertical **9:16**                                      |
| Resolução   | mínimo 540×960, recomendado **1080×1920**              |
| Duração     | de **3 a 90 segundos**                                 |
| Quadros/s   | de 24 a 60 fps                                         |

Se o vídeo não seguir essas regras, o envio pode até passar, mas o Facebook recusa
durante o processamento (o comando `status` mostra o motivo).

**Agendar um post** (o próprio Facebook publica na hora certa, o computador não
precisa ficar ligado):

```bash
python3 fb_bot.py publicar "Boa noite!" --quando 2026-11-20T21:00
```

**Agendar vários posts de uma vez** a partir de um arquivo JSON:

```bash
cp posts.exemplo.json posts.json   # edite com seus posts
python3 fb_bot.py agendar posts.json --simular   # confere sem enviar nada
python3 fb_bot.py agendar posts.json             # envia de verdade
```

Cada item do arquivo aceita os campos:

| Campo      | O que é                                                     |
|------------|-------------------------------------------------------------|
| `mensagem` | texto do post, legenda da foto ou descrição do Reel         |
| `link`     | link (em fotos e Reels, vai no fim do texto)                |
| `imagem`   | uma imagem (arquivo ou URL)                                 |
| `imagens`  | lista de imagens para um post com várias fotos              |
| `reel`     | vídeo do Reel (arquivo ou URL); não pode ter imagens junto  |
| `quando`   | data/hora para agendar; sem ele, publica na hora            |

Veja exemplos de cada tipo em `posts.exemplo.json`. Caminhos de arquivo podem ser
relativos à pasta onde você roda o comando ou à pasta `facebook_bot`. Depois de enviado, o bot grava o `id_facebook` no
próprio arquivo, então rodar de novo não duplica posts: é só acrescentar novos itens.

## 4. Horários fixos, legendas e hashtags (calendário)

O arquivo `calendario.json` define **em que horários** a Página posta e quais
**hashtags** e **assinatura** entram em todas as legendas:

```json
{
  "horarios": ["09:00", "12:30", "19:00"],
  "dias": ["seg", "ter", "qua", "qui", "sex", "sab", "dom"],
  "fuso": "-03:00",
  "hashtags": ["#meuamor", "#amor"],
  "assinatura": "💛 Siga a página para mais!"
}
```

| Campo        | O que é                                                          |
|--------------|------------------------------------------------------------------|
| `horarios`   | horários de postagem de cada dia                                 |
| `dias`       | dias da semana em que posta (`seg` a `dom`); sem ele, todos      |
| `fuso`       | fuso dos horários; `-03:00` é o horário de Brasília              |
| `hashtags`   | hashtags que vão em **todos** os posts                           |
| `assinatura` | frase que vai no fim de todas as legendas (opcional)             |

Se existir um `calendario.json` na mesma pasta do arquivo de posts, o comando
`agendar` usa ele automaticamente (ou indique outro com `--calendario arquivo.json`).

Com o calendário, você **não precisa escrever datas**: cada post sem `quando` vai para
o próximo horário livre, na ordem do arquivo. Cada post pode ter também as suas
próprias hashtags, que se somam às do calendário:

```json
[
  { "mensagem": "Bom dia! ☀️", "hashtags": ["#bomdia", "#motivação"] },
  { "mensagem": "Bastidores 🎬", "reel": "videos/bastidores.mp4", "hashtags": "#reels #bastidores" }
]
```

A legenda publicada fica assim:

```
Bom dia! ☀️

💛 Siga a página para mais!

#meuamor #amor #bomdia #motivação
```

Dicas:

- Rode com `--simular` para ver o dia, a hora e a legenda de cada post antes de enviar.
- As hashtags podem ser escritas com ou sem `#`; repetidas são ignoradas, e as que já
  estão no texto não são duplicadas.
- Um post com `quando` próprio usa esse horário (e aquele horário fica ocupado). Use
  `"quando": "agora"` para publicar na hora.
- O Facebook só agenda até 30 dias à frente. Se houver mais posts que horários livres
  nesse período, os que sobrarem esperam: é só rodar `agendar` de novo uns dias depois
  (pode adicionar posts novos no arquivo antes).
- Uma assinatura diferente num post específico: use `"assinatura"` no próprio post
  (`""` para nenhuma).

Para um post avulso, também dá para passar hashtags na linha de comando:

```bash
python3 fb_bot.py publicar "Pôr do sol 🌅" --imagem sol.jpg --hashtags "#natureza #pordosol"
```

### Regras do Facebook para agendamento

- O horário precisa estar entre **10 minutos** e **30 dias** no futuro.
- Sem fuso no horário (ex.: `2026-11-20T21:00`), vale o fuso do computador. Para
  fixar o horário de Brasília, use `2026-11-20T21:00-03:00`.
- Fotos e Reels não aceitam link como anexo, então o bot coloca o link no fim do texto.
- Reels agendados também seguem a regra dos 10 minutos a 30 dias.
- Os posts agendados aparecem no **Meta Business Suite → Planejador**, onde dá para
  editar ou cancelar.

## Testes

```bash
python3 -m unittest -v test_fb_bot
```

Os testes não acessam o Facebook (as chamadas de rede são simuladas).
