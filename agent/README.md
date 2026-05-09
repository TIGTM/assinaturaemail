# GTM Signature Agent

Cliente Windows que sincroniza a assinatura de e-mail do usuário com a VPS.

## Como funciona

1. Detecta o e-mail da conta Outlook do usuário (via env var Azure AD ou registry do Outlook)
2. Faz `GET https://assinatura.gtmalimentos.com.br/api/agent/signature?email=<x>`
3. Baixa a imagem da assinatura
4. Escreve em `%APPDATA%\Microsoft\Signatures\GTM Assinatura.{htm,txt,rtf}` + pasta de imagens
5. Configura registry do Outlook pra usar essa assinatura como padrão (novos e replies)
6. Reporta heartbeat pra VPS

## Teste manual (Phase 1)

Pré-requisitos: Python 3.10+ no PC.

```powershell
cd agent
python gtm_signature_agent.py
```

Logs em `%LOCALAPPDATA%\GTMSignatureAgent\agent.log`.

Após rodar, abrir Outlook → novo e-mail → confirmar que a assinatura aparece automaticamente.

## Empacotamento (Phase 2)

```powershell
pip install pyinstaller
pyinstaller --onefile --noconsole gtm_signature_agent.py
# Gera dist/gtm_signature_agent.exe
```

## Tarefa Agendada (Phase 2 — auto-instalado pelo MSI)

```powershell
# Dispara no logon do usuário
schtasks /Create /TN "GTM Signature Sync" `
  /TR "C:\Program Files\GTM Signature Agent\gtm_signature_agent.exe" `
  /SC ONLOGON /RL LIMITED /F

# Dispara também todo dia às 10h
schtasks /Create /TN "GTM Signature Sync Daily" `
  /TR "C:\Program Files\GTM Signature Agent\gtm_signature_agent.exe" `
  /SC DAILY /ST 10:00 /RL LIMITED /F
```

## Variáveis de ambiente opcionais

- `GTM_VPS_BASE` — sobrescreve o endereço da VPS (padrão: `https://assinatura.gtmalimentos.com.br`)

## Diagnóstico

Se a assinatura não aparecer:

1. Confirme a detecção do e-mail: olhe o log
2. Confirme que o e-mail bate com um funcionário no painel `/employees`
3. Confirme que existe imagem gerada no painel `/generate`
4. Confira no painel `/agents` se o heartbeat chegou
