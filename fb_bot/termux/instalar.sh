#!/data/data/com.termux/files/usr/bin/bash
# Instalador do fbbot para Android (Termux).
# Uso:  bash instalar.sh
set -e
BOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
echo "== Instalando o bot em $BOT_DIR =="

pkg update -y
pkg install -y python git termux-tools

echo "== Instalando bibliotecas Python =="
if ! pip install -r "$BOT_DIR/requirements.txt"; then
    echo "Tentando de novo com o compilador…"
    pkg install -y clang
    pip install -r "$BOT_DIR/requirements.txt"
fi

# Acesso à galeria/Downloads (o Android vai pedir permissão)
[ -d "$HOME/storage" ] || termux-setup-storage || true

# ---------- .env ----------
ENV="$BOT_DIR/.env"
if [ ! -f "$ENV" ]; then
    cp "$BOT_DIR/.env.example" "$ENV"
    echo
    echo "Cole o seu token do Facebook (FB_USER_TOKEN) e toque Enter:"
    read -r TOKEN
    sed -i "s|^FB_USER_TOKEN=.*|FB_USER_TOKEN=$TOKEN|" "$ENV"
    echo "App ID (Enter para pular):"; read -r APPID
    [ -n "$APPID" ] && sed -i "s|^FB_APP_ID=.*|FB_APP_ID=$APPID|" "$ENV"
    echo "App Secret (Enter para pular):"; read -r APPSECRET
    [ -n "$APPSECRET" ] && sed -i "s|^FB_APP_SECRET=.*|FB_APP_SECRET=$APPSECRET|" "$ENV"
    chmod 600 "$ENV"
fi

cd "$BOT_DIR"
if grep -q '^FB_APP_SECRET=.\+' "$ENV" && grep -q '^FB_APP_ID=.\+' "$ENV"; then
    echo "== Gerando token de longa duração (~60 dias) =="
    NEW=$(python -m fbbot token 2>/dev/null | tail -1) || true
    [ -n "$NEW" ] && case "$NEW" in ERRO*) ;; *) sed -i "s|^FB_USER_TOKEN=.*|FB_USER_TOKEN=$NEW|" "$ENV";; esac
fi

echo "== Suas páginas =="
if python -m fbbot pages; then
    if ! grep -q '^FB_PAGE_ID=.\+' "$ENV"; then
        echo "Digite o ID da página padrão (o número da primeira coluna):"
        read -r PAGEID
        sed -i "s|^FB_PAGE_ID=.*|FB_PAGE_ID=$PAGEID|" "$ENV"
    fi
else
    echo "Não consegui listar as páginas. Confira o token em $ENV (nano $ENV)"
fi

# ---------- Compartilhar vídeo da galeria -> Termux ----------
mkdir -p "$HOME/bin"
cat > "$HOME/bin/termux-file-editor" <<EOS
#!/data/data/com.termux/files/usr/bin/bash
exec bash "$BOT_DIR/termux/compartilhar.sh" "\$@"
EOS
chmod +x "$HOME/bin/termux-file-editor"

# ---------- Atalhos para o widget Termux:Widget ----------
mkdir -p "$HOME/.shortcuts"
cat > "$HOME/.shortcuts/Painel do Bot" <<EOS
#!/data/data/com.termux/files/usr/bin/bash
cd "$BOT_DIR"
termux-wake-lock
(sleep 3; termux-open-url http://localhost:8000) &
python -m fbbot painel
EOS
cat > "$HOME/.shortcuts/Fila de Reels" <<EOS
#!/data/data/com.termux/files/usr/bin/bash
cd "$BOT_DIR"
termux-wake-lock
python -m fbbot fila
EOS
chmod +x "$HOME/.shortcuts/"*

echo
echo "✅ Pronto!"
echo " • Painel:       cd $BOT_DIR && python -m fbbot painel   (abra http://localhost:8000)"
echo " • Compartilhar: na Galeria, toque em Compartilhar > Termux > 'Edit' (ou Abrir) num vídeo"
echo " • Widget:       instale o app Termux:Widget para ter os atalhos na tela inicial"
