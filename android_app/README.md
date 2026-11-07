# Postador Meu Amor (app Android)

App para o celular que publica e agenda **fotos**, **Reels** e posts de texto na sua
**Página do Facebook**, com **horários fixos**, **legendas** e **hashtags**. Faz o mesmo que
o bot em Python (`facebook_bot/`), mas direto no celular.

- Android 8.0 ou mais novo.
- Não precisa de servidor nem de deixar o celular ligado: quem publica na hora marcada é
  o próprio Facebook.
- O app só conversa com o Facebook (graph.facebook.com). Nenhum dado vai para outro lugar.

## Instalar o APK

1. Baixe o arquivo `PostadorMeuAmor.apk` no celular.
2. Toque nele para abrir. O Android vai pedir para **permitir a instalação de apps
   desta fonte** (do navegador ou do gerenciador de arquivos): permita e volte.
3. Toque em **Instalar**. Se o Google Play Protect avisar que o app é desconhecido,
   toque em **Mais detalhes → Instalar mesmo assim**: isso acontece com todo app que
   não vem da Play Store.

## Usar

### Aba Conta (primeira vez)

O passo a passo também aparece dentro do app:

1. Toque em **Abrir meus apps da Meta**, crie um app com o caso de uso
   **Gerenciar tudo na sua Página** e copie o **App ID** e o **App Secret**
   (Configurações do app → Básico).
2. Toque em **Abrir o Graph API Explorer**, escolha o seu app, adicione as permissões
   `pages_show_list`, `pages_read_engagement` e `pages_manage_posts`, toque em
   **Generate Access Token**, marque a sua Página e copie o token.
3. Cole o App ID, o App Secret e o token no app e toque em **Conectar**.

O app troca o token por um **token da Página que não expira** e avisa se faltar
alguma permissão. O App Secret não fica salvo.

> Dica: o site da Meta funciona melhor no modo "Versão para computador" do navegador.

### Aba Horários

- **Horários de postagem**: por exemplo `09:00, 12:30, 19:00`.
- **Dias da semana** em que a Página posta.
- **Hashtags em todos os posts** e uma **assinatura** opcional (ex.: "💛 Siga a página!").

Mostra também os próximos horários livres e o histórico do que foi enviado.

### Aba Postar

1. Toque em **📷 Fotos** (uma ou várias, que saem juntas num post) ou **🎬 Reel**
   (vídeo vertical 9:16, de 3 a 90 segundos). Sem mídia, o post é só de texto.
2. Escreva a **legenda** e, se quiser, **hashtags só deste post**.
3. Escolha **quando**:
   - **No próximo horário livre** (dos horários que você definiu);
   - **Escolher dia e hora**;
   - **Agora**.
4. Confira a **prévia da legenda** (texto + assinatura + hashtags) e toque em
   **Agendar** / **Publicar agora**.

Também dá para abrir a **galeria**, selecionar fotos ou um vídeo e tocar em
**Compartilhar → Postador Meu Amor**.

Para editar ou cancelar um post já agendado, use o **Meta Business Suite → Planejador**.

### Limites do Facebook

- Agendamento: de **10 minutos** a **30 dias** à frente.
- Reels: `.mp4` vertical 9:16, de 3 a 90 segundos. Depois de enviar, toque em
  **Ver se o Reel já foi processado**: o Facebook leva alguns minutos.
- Mantenha o app aberto enquanto um vídeo está sendo enviado.

## Para desenvolvedores

Projeto Gradle em Java, sem bibliotecas externas (só o Android).

```bash
cd android_app
./gradlew testDebugUnitTest   # testes (JUnit + Robolectric)
./gradlew assembleRelease     # APK em app/build/outputs/apk/release/app-release.apk
```

Precisa do Android SDK (variável `ANDROID_HOME` ou `local.properties` com `sdk.dir`).
Cada push que altera `android_app/` também gera o APK no GitHub Actions
(aba **Actions** → execução → **Artifacts**).

O APK é assinado com `app/postador.keystore` (senha `postador`), que fica no repositório
para que as próximas versões possam ser instaladas **por cima** da anterior sem perder
os dados. Essa chave é só para uso pessoal: para publicar na Play Store, crie uma chave
nova e guarde-a fora do repositório.
