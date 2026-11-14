# Bot de postagem para o Facebook

Publica e agenda **fotos**, **Reels** e posts de texto/link numa **Página do Facebook**
usando a Graph API oficial. Só usa a biblioteca padrão do Python 3.9+ (sem `pip install`).

> ⚠️ A API do Facebook só permite postar em **Páginas**. Perfis pessoais não aceitam
> postagem automática, e a postagem em Grupos pela API foi desativada pela Meta em 2024.

## 1. Conectar o bot ao Facebook (API)

Você vai precisar de: uma conta pessoal do Facebook que seja **administradora da
Página** e uns 10 minutos. Não precisa pagar nada nem enviar o app para análise da
Meta: como o app é só seu e posta na sua própria Página, ele funciona no modo de
desenvolvimento.

### Passo 1: virar desenvolvedor (só na primeira vez)

1. Entre em <https://developers.facebook.com> com a sua conta do Facebook.
2. Clique em **Começar** (*Get Started*) e siga o cadastro (confirmar telefone/e-mail).

### Passo 2: criar o app

1. Vá em <https://developers.facebook.com/apps> e clique em **Criar app** (*Create App*).
2. Dê um nome (ex.: `Bot Meu Amor`) e informe seu e-mail.
3. No **caso de uso**, escolha **Gerenciar tudo na sua Página**
   (*Manage everything on your Page*).
4. Se perguntar por portfólio empresarial, pode escolher **Ainda não quero conectar**
   um portfólio. Conclua a criação.
5. No painel do app, abra **Casos de uso → Gerenciar tudo na sua Página →
   Personalizar** e confirme que estas permissões estão adicionadas:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`.

### Passo 3: copiar o App ID e o App Secret

No menu do app, vá em **Configurações do app → Básico** (*App settings → Basic*):

- **ID do app** (*App ID*): um número.
- **Chave secreta do app** (*App Secret*): clique em **Mostrar** e copie.

> 🔒 O App Secret é uma senha. Não mande para ninguém nem coloque no GitHub.

### Passo 4: gerar o token no Graph API Explorer

1. Abra <https://developers.facebook.com/tools/explorer>.
2. À direita, em **Meta App**, escolha o app que você criou.
3. Em **User or Page**, deixe **User Token** (token do usuário).
4. Em **Permissions**, adicione: `pages_show_list`, `pages_read_engagement` e
   `pages_manage_posts`.
5. Clique em **Generate Access Token**. Na janela do Facebook, clique em
   **Editar acesso** / **Continuar**, **marque todas as Páginas** que o bot vai usar
   e confirme.
6. Copie o token que apareceu no campo **Access Token** (um texto longo que começa
   com `EAA...`). Ele vale só ~1 hora, mas o próximo passo resolve isso.

### Passo 5: rodar o `conectar`

No computador, dentro da pasta do bot:

```bash
cd facebook_bot
python3 fb_bot.py conectar
```

O bot pede o **App ID**, o **App Secret** e o **token** (o que você colar nos dois
últimos não aparece na tela, isso é normal). Ele então:

1. troca o token de 1 hora por um token de longa duração;
2. pega o **token de cada Página** que você autorizou (esses tokens **não expiram**);
3. se houver mais de uma Página, pergunta qual será a **Página padrão** (a usada
   quando o post não diz em qual Página sai);
4. grava as Páginas e os tokens no arquivo `facebook_bot/paginas.json`.

O App Secret **não** é gravado. Para conferir:

```bash
python3 fb_bot.py verificar
# ✅ Meu Amor (id 1234...)
# ✅ Minha Loja (id 5678...)
python3 fb_bot.py paginas                    # lista as Páginas conectadas
python3 fb_bot.py paginas --padrao "Minha Loja"   # muda a Página padrão
```

Criou uma Página nova ou esqueceu de marcar alguma? Gere outro token marcando todas e
rode `conectar` de novo: a Página padrão continua a mesma.

Pronto: o bot está conectado.

> No Windows, use `python` ou `py` no lugar de `python3`.

### Se algo der errado

| Mensagem                                    | O que fazer                                                       |
|---------------------------------------------|-------------------------------------------------------------------|
| `Nenhuma Página encontrada`                 | Gere o token de novo e, na janela do Facebook, marque a Página.   |
| `faltam as permissões ...`                  | Adicione as permissões que faltam no Explorer e gere de novo.     |
| `(190) ... token inválido ou expirado`      | O token do Explorer passou de 1 hora: gere outro e rode `conectar`. |
| `(10)` ou `(200) ... permissão faltando`    | Você precisa ser administrador da Página e ter as 3 permissões.   |
| Erro sobre App Secret / `client_secret`     | Confira o App Secret em Configurações do app → Básico.            |

O token da Página para de funcionar se você trocar a senha do Facebook, perder a
função de administrador da Página ou remover o app nas configurações. Nesses casos, é
só repetir os passos 4 e 5.

**Os posts não aparecem para o público?** Apps em modo de desenvolvimento podem ter
alcance limitado. Nesse caso, publique o app: no painel, preencha a **URL da política
de privacidade** em Configurações do app → Básico e mude o app para o modo **Ao vivo**
(*Live*).

### Configurar à mão (opcional)

Se já tiver um token de Página, copie `.env.exemplo` para `.env` e preencha
`FB_PAGE_ID` e `FB_PAGE_ACCESS_TOKEN` (isso configura uma Página só; se existir um
`paginas.json`, ele tem prioridade). O `.env` e o `paginas.json` estão no `.gitignore`:
**nunca** faça commit deles. Também dá para usar variáveis de ambiente com esses mesmos nomes.

## 2. Usar

### Em qual Página o post sai

Sem dizer nada, o post sai na **Página padrão**. Para escolher:

```bash
python3 fb_bot.py publicar "Promoção!" --pagina "Minha Loja"
python3 fb_bot.py publicar "Novidade" --pagina "Meu Amor" --pagina "Minha Loja"
python3 fb_bot.py publicar "Aviso para todas" --todas
```

O nome da Página pode ser escrito com maiúsculas ou minúsculas (ou use o id). No
arquivo de posts, use o campo `"paginas"` (veja a seção de agendamento).

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
| `paginas`  | Página(s) onde sai: `"Minha Loja"`, `["Meu Amor", "Minha Loja"]` ou `"todas"`; sem ele, a Página padrão |

Veja exemplos de cada tipo em `posts.exemplo.json`. Caminhos de arquivo podem ser
relativos à pasta onde você roda o comando ou à pasta `facebook_bot`.

Depois de enviado, o bot anota no campo `enviados` em quais Páginas o post já saiu,
então rodar de novo não duplica posts: é só acrescentar novos itens. Se uma das
Páginas der erro, rodar de novo tenta **só** a que faltou.

## 3. Horários fixos, legendas e hashtags (calendário)

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
