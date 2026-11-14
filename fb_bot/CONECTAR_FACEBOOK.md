# Como conectar o Meu Bot Reels ao seu Facebook

Você faz isso **uma vez só**. Depois, basta tocar em **Entrar com Facebook** no app.

## 1. Criar o app no Facebook

1. Entre em **developers.facebook.com** com a sua conta do Facebook e toque em **Meus apps → Criar app**.
2. Escolha o caso de uso **"Gerenciar tudo na sua Página"** (ou "Outro" → tipo **Empresa**).
3. Dê um nome (ex.: *Meu Bot Reels*) e crie.

## 2. Configurar o login

1. No painel do app, abra **Login do Facebook** (ou **Login do Facebook para Empresas**) → **Configurações**.
2. Em **URIs de redirecionamento do OAuth válidos**, adicione:
   ```
   https://mika4747.github.io/Meu_Amor/fb-callback.html
   ```
3. Deixe ligados **Login do OAuth do cliente** e **Login do OAuth na Web**. Salve.
4. Em **Configurações do app → Básico**, adicione `mika4747.github.io` em **Domínios do app** e salve.
5. **Só se o app for do tipo Empresa:** em **Login do Facebook para Empresas → Configurações**, crie uma
   *configuração* com o tipo de token **Token de acesso do usuário** e as permissões `pages_show_list`,
   `pages_read_engagement` e `pages_manage_posts`. Copie o **Config ID** gerado.

## 3. Conectar no app

1. Em **Configurações do app → Básico**, copie o **App ID** e o **App Secret** (toque em *Mostrar*).
2. No Meu Bot Reels, cole o App ID e o App Secret. Se o app for do tipo Empresa, cole também o Config ID.
3. Toque em **Entrar com Facebook**, faça login, **marque as suas Páginas** e autorize.
4. Você volta para o app já conectado ✅

> O App Secret faz a conexão durar para sempre (tokens de Página permanentes). Ele fica salvo só no seu
> celular. Sem ele, a conexão expira em cerca de 1 hora.

> Enquanto o app do Facebook estiver em **modo Desenvolvimento**, só você (administrador do app) consegue
> fazer login. Para uso pessoal isso basta, e não é preciso revisão do Facebook.

## Problemas comuns

| Mensagem | Solução |
|---|---|
| "URL bloqueada" / "redirect_uri" | Confira o endereço do passo 2.2, sem espaços e com `https` |
| "Domínio não incluído" | Faça o passo 2.4 |
| "Nenhuma página encontrada" | No login, toque em *Editar acesso* e marque as suas Páginas |
| Página do Facebook abre, mas não volta ao app | Toque no botão **Abrir o app** da página |
