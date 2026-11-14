#!/data/data/com.termux/files/usr/bin/bash
# Chamado quando você compartilha um vídeo da Galeria para o Termux.
BOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VIDEO="$1"
cd "$BOT_DIR" || exit 1

case "${VIDEO,,}" in
    *.mp4|*.mov|*.m4v) ;;
    *) echo "Isso não parece um vídeo: $VIDEO"; read -rp "Enter para sair"; exit 1;;
esac

echo "🎬 Vídeo recebido: $(basename "$VIDEO")"
echo
echo "Legenda (Enter para nenhuma):"
read -r LEGENDA
echo
echo "O que fazer?"
echo "  1) Publicar agora"
echo "  2) Agendar"
echo "  3) Colocar na fila"
read -rp "Escolha [1]: " OP

termux-wake-lock 2>/dev/null
case "$OP" in
    2)
        read -rp "Data e hora (AAAA-MM-DD HH:MM): " QUANDO
        python -m fbbot reel "$VIDEO" -d "$LEGENDA" --agendar "$QUANDO"; RC=$?
        ;;
    3)
        FILA="$(grep '^FB_QUEUE_DIR=' .env | cut -d= -f2-)"; FILA="${FILA:-fila}"
        mkdir -p "$FILA"
        NOME="$(date +%Y%m%d_%H%M%S)_$(basename "$VIDEO")"
        cp "$VIDEO" "$FILA/$NOME" && printf '%s\n' "$LEGENDA" > "$FILA/${NOME%.*}.txt"; RC=$?
        [ $RC -eq 0 ] && echo "📥 Adicionado à fila: $NOME"
        ;;
    *)
        python -m fbbot reel "$VIDEO" -d "$LEGENDA"; RC=$?
        ;;
esac
termux-wake-unlock 2>/dev/null

# O Termux guarda uma cópia do arquivo compartilhado em ~/downloads; apaga para não ocupar espaço
case "$VIDEO" in "$HOME"/downloads/*) rm -f "$VIDEO";; esac

echo
if [ $RC -eq 0 ]; then echo "✅ Feito!"; else echo "❌ Deu erro (veja acima)."; fi
read -rp "Enter para fechar"
