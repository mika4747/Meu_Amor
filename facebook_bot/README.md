# Bot de postagem para o Facebook

Publica e agenda posts (texto, link e/ou imagem) numa **Página do Facebook** usando a
Graph API oficial. Só usa a biblioteca padrão do Python 3.9+ (sem `pip install`).

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

Cada item do arquivo aceita os campos `mensagem`, `link`, `imagem` e `quando`
(sem `quando`, publica na hora). Depois de enviado, o bot grava o `id_facebook` no
próprio arquivo, então rodar de novo não duplica posts: é só acrescentar novos itens.

### Regras do Facebook para agendamento

- O horário precisa estar entre **10 minutos** e **30 dias** no futuro.
- Sem fuso no horário (ex.: `2026-11-20T21:00`), vale o fuso do computador. Para
  fixar o horário de Brasília, use `2026-11-20T21:00-03:00`.
- Post com imagem **e** link: a API não aceita os dois juntos, então o bot coloca o
  link no fim da legenda da foto.
- Os posts agendados aparecem no **Meta Business Suite → Planejador**, onde dá para
  editar ou cancelar.

## Testes

```bash
python3 -m unittest -v test_fb_bot
```

Os testes não acessam o Facebook (as chamadas de rede são simuladas).
