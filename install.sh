#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  GTM Signature App — Script de instalação para Ubuntu 20.04 / 22.04
#  Execute como root ou com sudo: bash install.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="python3"
SERVICE_USER="www-data"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   GTM Signature App — Instalação             ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ─── 1. Atualizar sistema e instalar dependências base ───────────────────────
echo "→ Atualizando pacotes..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    nginx \
    curl wget \
    fonts-dejavu fonts-liberation \
    software-properties-common

# ─── 2. PowerShell Core ──────────────────────────────────────────────────────
echo ""
echo "→ Instalando PowerShell Core..."
if ! command -v pwsh &> /dev/null; then
    # Detecta versão do Ubuntu
    UBUNTU_VERSION=$(lsb_release -rs 2>/dev/null || echo "22.04")
    wget -q "https://packages.microsoft.com/config/ubuntu/${UBUNTU_VERSION}/packages-microsoft-prod.deb" \
         -O /tmp/packages-microsoft-prod.deb
    dpkg -i /tmp/packages-microsoft-prod.deb
    apt-get update -qq
    apt-get install -y -qq powershell
    echo "   PowerShell Core instalado: $(pwsh --version)"
else
    echo "   PowerShell Core já instalado: $(pwsh --version)"
fi

# ─── 3. Módulo ExchangeOnlineManagement ──────────────────────────────────────
echo ""
echo "→ Instalando módulo ExchangeOnlineManagement..."
pwsh -NonInteractive -Command "
    if (-not (Get-Module -ListAvailable -Name ExchangeOnlineManagement)) {
        Install-Module -Name ExchangeOnlineManagement -Force -AllowClobber -Scope AllUsers
        Write-Host '   Módulo instalado.'
    } else {
        Write-Host '   Módulo já instalado.'
    }
"

# ─── 4. Ambiente Python ───────────────────────────────────────────────────────
echo ""
echo "→ Criando ambiente virtual Python..."
cd "$APP_DIR"
$PYTHON_BIN -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "   Dependências Python instaladas."

# ─── 5. Arquivo .env ─────────────────────────────────────────────────────────
echo ""
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo "   ✅ Arquivo .env criado a partir do .env.example"
    echo "   ⚠️  EDITE o arquivo .env antes de iniciar a aplicação!"
else
    echo "   .env já existe, mantendo configurações atuais."
fi

# ─── 6. Permissões ───────────────────────────────────────────────────────────
echo ""
echo "→ Configurando permissões..."
mkdir -p "$APP_DIR/static/signatures" "$APP_DIR/static/uploads" "$APP_DIR/fonts"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/static" "$APP_DIR/fonts" 2>/dev/null || true
chmod -R 755 "$APP_DIR/static"

# ─── 7. Serviço systemd ───────────────────────────────────────────────────────
echo ""
echo "→ Criando serviço systemd..."
cat > /etc/systemd/system/gtm-signatures.service << EOF
[Unit]
Description=GTM Signature App
After=network.target

[Service]
User=root
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/venv/bin/python ${APP_DIR}/app.py
Restart=always
RestartSec=5
Environment=PATH=${APP_DIR}/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable gtm-signatures
echo "   Serviço gtm-signatures criado e habilitado."

# ─── 8. Nginx ─────────────────────────────────────────────────────────────────
echo ""
echo "→ Configurando Nginx..."
cat > /etc/nginx/sites-available/gtm-signatures << 'NGINX'
server {
    listen 80;
    server_name _;

    # Redireciona HTTP → HTTPS (descomente após configurar SSL)
    # return 301 https://$host$request_uri;

    location /static/ {
        alias APP_DIR_PLACEHOLDER/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    location / {
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
NGINX

# Substitui o placeholder pelo caminho real
sed -i "s|APP_DIR_PLACEHOLDER|${APP_DIR}|g" /etc/nginx/sites-available/gtm-signatures

# Ativa o site
ln -sf /etc/nginx/sites-available/gtm-signatures /etc/nginx/sites-enabled/gtm-signatures
rm -f /etc/nginx/sites-enabled/default

nginx -t && systemctl reload nginx
echo "   Nginx configurado."

# ─── 9. Certificado para Exchange Online ─────────────────────────────────────
echo ""
echo "→ Gerando certificado para autenticação no Exchange Online..."
CERT_DIR="$APP_DIR/cert"
mkdir -p "$CERT_DIR"

if [ ! -f "$CERT_DIR/exchange.pfx" ]; then
    openssl req -x509 -nodes -newkey rsa:2048 -keyout "$CERT_DIR/exchange.key" \
        -out "$CERT_DIR/exchange.crt" -days 730 \
        -subj "/CN=GTMSignatureApp/O=GTMAlimentos/C=BR" 2>/dev/null

    openssl pkcs12 -export \
        -out "$CERT_DIR/exchange.pfx" \
        -inkey "$CERT_DIR/exchange.key" \
        -in "$CERT_DIR/exchange.crt" \
        -passout pass:gtm@signatures2025

    THUMBPRINT=$(openssl x509 -in "$CERT_DIR/exchange.crt" -fingerprint -noout \
                 | sed 's/SHA1 Fingerprint=//' | tr -d ':')

    echo ""
    echo "   ✅ Certificado gerado em: $CERT_DIR/exchange.pfx"
    echo "   📋 Thumbprint do certificado:"
    echo "      $THUMBPRINT"
    echo ""
    echo "   ➡️  Adicione ao .env:"
    echo "      EXCHANGE_CERT_PATH=${CERT_DIR}/exchange.pfx"
    echo "      EXCHANGE_CERT_PASSWORD=gtm@signatures2025"
    echo "      EXCHANGE_CERT_THUMBPRINT=${THUMBPRINT}"
    echo ""
    echo "   ➡️  Faça upload do arquivo exchange.crt no Azure AD App Registration."
else
    echo "   Certificado já existe em $CERT_DIR/exchange.pfx"
fi

# ─── Finalização ──────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  ✅ Instalação concluída!                                    ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Próximos passos:                                            ║"
echo "║                                                              ║"
echo "║  1. Edite o arquivo .env com suas credenciais               ║"
echo "║  2. Siga o SETUP.md para configurar o Azure AD              ║"
echo "║  3. Inicie a aplicação: systemctl start gtm-signatures      ║"
echo "║  4. Acesse: http://SEU-DOMINIO (senha definida no .env)     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
