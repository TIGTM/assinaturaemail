#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  GTM Signature App — Download de fontes
#  Execute na VPS: bash download_fonts.sh
# ─────────────────────────────────────────────────────────────────

FONTS_DIR="$(cd "$(dirname "$0")" && pwd)/fonts"
mkdir -p "$FONTS_DIR"

echo "→ Baixando fontes Montserrat (Google Fonts)..."

BASE="https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf"

declare -A FONTS=(
  ["Montserrat-Regular.ttf"]="$BASE/Montserrat-Regular.ttf"
  ["Montserrat-Bold.ttf"]="$BASE/Montserrat-Bold.ttf"
  ["Montserrat-SemiBold.ttf"]="$BASE/Montserrat-SemiBold.ttf"
  ["Montserrat-Light.ttf"]="$BASE/Montserrat-Light.ttf"
  ["Montserrat-Medium.ttf"]="$BASE/Montserrat-Medium.ttf"
)

for filename in "${!FONTS[@]}"; do
  url="${FONTS[$filename]}"
  dest="$FONTS_DIR/$filename"
  if [ ! -f "$dest" ]; then
    echo "   Baixando $filename..."
    wget -q "$url" -O "$dest" && echo "   ✅ $filename" || echo "   ❌ Falha: $filename"
  else
    echo "   ✅ $filename já existe"
  fi
done

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Fontes Montserrat instaladas!                       ║"
echo "║                                                      ║"
echo "║  ⚠️  ATENÇÃO: Serão CY Grotesk Wide é uma fonte     ║"
echo "║  comercial. Você precisa:                            ║"
echo "║  1. Obter o arquivo .ttf com o fornecedor/designer  ║"
echo "║  2. Copiar para: $FONTS_DIR                         ║"
echo "║     - SeraoCYGroteskWide-Bold.ttf                   ║"
echo "║     - SeraoCYGroteskWide-Regular.ttf                ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "Fontes disponíveis em $FONTS_DIR:"
ls "$FONTS_DIR"
