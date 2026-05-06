# GTM Signature App — Guia de Configuração

## Passo 1 — Instalar na VPS

```bash
# No servidor Ubuntu, clone/copie os arquivos e execute:
chmod +x install.sh
sudo bash install.sh
```

O script instala automaticamente: Python, PowerShell Core, módulo ExchangeOnlineManagement,
Nginx, gera o certificado e cria o serviço systemd.

---

## Passo 2 — Registrar App no Azure AD (leitura de usuários)

> Acesse: https://portal.azure.com → Azure Active Directory → App registrations

1. Clique em **+ New registration**
2. Nome: `GTM Signature App`
3. Supported account types: **Accounts in this organizational directory only**
4. Clique em **Register**

### Copie os IDs:
- **Application (client) ID** → `AZURE_CLIENT_ID` no .env
- **Directory (tenant) ID** → `AZURE_TENANT_ID` no .env

### Criar Client Secret:
1. Certificates & secrets → **+ New client secret**
2. Descrição: `gtm-signatures`, Expiration: 24 months
3. Copie o **Value** → `AZURE_CLIENT_SECRET` no .env

### Adicionar permissão de leitura de usuários:
1. API permissions → **+ Add a permission** → Microsoft Graph
2. Application permissions → procure `User.Read.All`
3. Adicione e clique em **Grant admin consent**

---

## Passo 3 — Registrar App no Azure AD (deploy de assinaturas)

> Você pode usar o **mesmo app** ou criar um separado para o Exchange.

### Fazer upload do certificado:
1. No app registration → **Certificates & secrets** → Certificates
2. Clique em **Upload certificate**
3. Faça upload do arquivo `cert/exchange.crt` gerado pelo install.sh
4. Copie o **Thumbprint** → `EXCHANGE_CERT_THUMBPRINT` no .env

### Adicionar permissão no Exchange Online:
1. API permissions → **+ Add a permission** → APIs my organization uses
2. Procure **Office 365 Exchange Online**
3. Application permissions → `Exchange.ManageAsApp`
4. **Grant admin consent**

### Atribuir papel no Exchange:
```powershell
# Execute no PowerShell como admin do Exchange Online
Connect-ExchangeOnline -UserPrincipalName admin@suaempresa.com
New-ManagementRoleAssignment `
    -App "GTM Signature App" `
    -Role "Application Impersonation" `
    -CustomRecipientWriteScope "Default Role Assignment Policy"
Disconnect-ExchangeOnline -Confirm:$false
```

---

## Passo 4 — Configurar o .env

```env
VPS_BASE_URL=https://assinaturas.gtmalimentos.com.br
SECRET_KEY=gere-uma-chave-aleatoria-aqui

AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_SECRET=seu-client-secret-aqui
M365_DOMAIN=gtmalimentos.com.br

EXCHANGE_APP_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
EXCHANGE_CERT_THUMBPRINT=AABBCCDDEEFF...
EXCHANGE_CERT_PATH=/caminho/para/cert/exchange.pfx
EXCHANGE_CERT_PASSWORD=gtm@signatures2025
EXCHANGE_ORGANIZATION=gtmalimentos.onmicrosoft.com

ADMIN_PASSWORD=senha-forte-aqui
```

---

## Passo 5 — Iniciar a aplicação

```bash
systemctl start gtm-signatures
systemctl status gtm-signatures   # verificar se está rodando
```

Acesse: **http://seu-dominio** com a senha definida em `ADMIN_PASSWORD`.

---

## Passo 6 — SSL (HTTPS) com Let's Encrypt

```bash
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d assinaturas.gtmalimentos.com.br
```

Depois descomente a linha de redirect HTTP→HTTPS no arquivo
`/etc/nginx/sites-available/gtm-signatures`.

---

## Passo 7 — Ativar Roaming Signatures no tenant

Para que as assinaturas definidas via OWA sincronizem para o **Outlook Desktop**:

```powershell
Connect-ExchangeOnline -UserPrincipalName admin@gtmalimentos.com.br
Set-OrganizationConfig -SignatureRoamingEnabled $true
Disconnect-ExchangeOnline -Confirm:$false
```

---

## Fluxo de uso no dia a dia

```
1. Marketing envia nova imagem base (sem dados)
2. Admin faz upload em: Layouts → Novo layout
3. Posiciona os campos no editor visual
4. Ativa o layout
5. Clica em "Gerar imagens" → seleciona todos
6. Clica em "Deploy M365" → seleciona todos
7. Pronto! Todos os emails atualizados automaticamente.
```

## Quando um funcionário muda de cargo/telefone

```
1. Employees → editar funcionário (ou sincronizar Azure AD)
2. Gerar imagens → selecionar só esse funcionário
3. Deploy M365 → selecionar só esse funcionário
```

A imagem é sobrescrita na VPS com o mesmo nome de arquivo, então o Exchange
usa automaticamente a versão atualizada sem precisar de novo deploy.
