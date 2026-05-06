#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  GTM Signature App — Reinstalação sem conflito de porta
#  Roda na porta 5001 diretamente, sem Nginx
#  Execute: sudo bash reinstall.sh
# ─────────────────────────────────────────────────────────────────

set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "→ Parando serviços anteriores..."
systemctl stop gtm-signatures 2>/dev/null || true
systemctl disable gtm-signatures 2>/dev/null || true

echo "→ Removendo config Nginx do app (mantém outras apps intactas)..."
rm -f /etc/nginx/sites-enabled/gtm-signatures
rm -f /etc/nginx/sites-available/gtm-signatures
nginx -t 2>/dev/null && systemctl reload nginx 2>/dev/null || true

echo "→ Instalando dependências Python..."
cd "$APP_DIR"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "→ Criando pastas necessárias..."
mkdir -p static/signatures static/uploads fonts cert

echo "→ Abrindo porta 5001 no firewall..."
ufw allow 5001/tcp 2>/dev/null || true
iptables -I INPUT -p tcp --dport 5001 -j ACCEPT 2>/dev/null || true

echo "→ Criando serviço systemd na porta 5001..."
cat > /etc/systemd/system/gtm-signatures.service << EOF
[Unit]
Description=GTM Signature App (porta 5001)
After=network.target

[Service]
User=root
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/venv/bin/python ${APP_DIR}/app.py
Restart=always
RestartSec=5
Environment=PATH=${APP_DIR}/venv/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable gtm-signatures
systemctl start gtm-signatures

sleep 2

echo ""
if systemctl is-active --quiet gtm-signatures; then
    echo "╔══════════════════════════════════════════════════╗"
    echo "║  ✅ GTM Signature App rodando!                   ║"
    echo "║                                                  ║"
    echo "║  Acesse: http://82.29.62.7:5001                 ║"
    echo "║  Senha:  definida em ADMIN_PASSWORD no .env     ║"
    echo "╚══════════════════════════════════════════════════╝"
else
    echo "⚠️  Serviço não iniciou. Veja o log:"
    journalctl -u gtm-signatures -n 20 --no-pager
fi
