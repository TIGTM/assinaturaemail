"""
signature_deployer.py — Deploy de assinaturas no Microsoft 365
Usa PowerShell Core + módulo ExchangeOnlineManagement para definir
a assinatura HTML de cada funcionário via Set-MailboxMessageConfiguration.

Pré-requisitos na VPS:
  - PowerShell Core instalado  (pwsh)
  - Módulo ExchangeOnlineManagement instalado
  - Certificado .pfx registrado no Azure AD App Registration

Autenticação usada: App-Only (Certificate)
  - Mais segura que usuário/senha
  - Não requer MFA
  - Documentação: https://learn.microsoft.com/exchange/client-developer/exchange-web-services/how-to-authenticate-an-ews-application-by-using-oauth
"""
import os
import json
import subprocess
import tempfile
import textwrap
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class SignatureDeployer:
    """
    Deploya assinaturas HTML no Exchange Online via PowerShell.
    """

    def __init__(self):
        self.app_id        = os.getenv("EXCHANGE_APP_ID")
        self.cert_thumb    = os.getenv("EXCHANGE_CERT_THUMBPRINT")
        self.organization  = os.getenv("EXCHANGE_ORGANIZATION")
        self.cert_path     = os.getenv("EXCHANGE_CERT_PATH", "")      # .pfx opcional
        self.cert_password = os.getenv("EXCHANGE_CERT_PASSWORD", "")  # senha do .pfx
        self.signature_name = os.getenv("EXCHANGE_SIGNATURE_NAME", "GTM Assinatura")
        self._ps_available = self._check_powershell()

    # ─── Verificações ─────────────────────────────────────────────────────────

    def _check_powershell(self) -> bool:
        """Verifica se o PowerShell Core (pwsh) está disponível."""
        try:
            r = subprocess.run(
                ["pwsh", "-Command", "echo ok"],
                capture_output=True, text=True, timeout=10
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def is_configured(self) -> tuple[bool, str]:
        """Verifica se todas as configurações necessárias estão presentes."""
        if not self._ps_available:
            return False, "PowerShell Core (pwsh) não encontrado. Execute o install.sh."
        if not self.app_id:
            return False, "EXCHANGE_APP_ID não configurado no .env"
        if not self.cert_thumb and not self.cert_path:
            return False, "Configure EXCHANGE_CERT_THUMBPRINT ou EXCHANGE_CERT_PATH no .env"
        if not self.organization:
            return False, "EXCHANGE_ORGANIZATION não configurado no .env"
        return True, "OK"

    # ─── Deploy individual ────────────────────────────────────────────────────

    def deploy(self, email: str, signature_html: str) -> tuple[bool, str]:
        """
        Define a assinatura HTML para um usuário no Exchange Online.
        Retorna (sucesso: bool, mensagem: str).
        """
        ok, msg = self.is_configured()
        if not ok:
            return False, msg

        # Escapa aspas simples para uso em strings single-quoted no PowerShell.
        safe_html = signature_html.replace("'", "''")
        safe_signature_name = self.signature_name.replace("'", "''")

        # Constrói script PowerShell
        if self.cert_path and Path(self.cert_path).exists():
            connect_cmd = textwrap.dedent(f"""
                $SecurePass = ConvertTo-SecureString '{self.cert_password}' -AsPlainText -Force
                Connect-ExchangeOnline `
                    -AppId '{self.app_id}' `
                    -CertificateFilePath '{self.cert_path}' `
                    -CertificatePassword $SecurePass `
                    -Organization '{self.organization}' `
                    -ShowBanner:$false
            """)
        else:
            connect_cmd = textwrap.dedent(f"""
                Connect-ExchangeOnline `
                    -AppId '{self.app_id}' `
                    -CertificateThumbprint '{self.cert_thumb}' `
                    -Organization '{self.organization}' `
                    -ShowBanner:$false
            """)

        script = textwrap.dedent(f"""
            $ErrorActionPreference = 'Stop'
            try {{
                {connect_cmd}
                $signatureName = '{safe_signature_name}'
                $signatureHtml = '{safe_html}'

                try {{
                    # Exchange Online com roaming signatures (new Outlook/OWA).
                    Set-MailboxMessageConfiguration `
                        -Identity '{email}' `
                        -SignatureName $signatureName `
                        -SignatureHtmlBody $signatureHtml `
                        -DefaultSignature $signatureName `
                        -DefaultSignatureOnReply $signatureName `
                        -DefaultFormat Html `
                        -AutoAddSignature $true `
                        -AutoAddSignatureOnReply $true `
                        -ErrorAction Stop
                }} catch {{
                    # Fallback legado para tenants/cmdlets sem parâmetros de roaming.
                    Set-MailboxMessageConfiguration `
                        -Identity '{email}' `
                        -SignatureHtml $signatureHtml `
                        -DefaultFormat Html `
                        -AutoAddSignature $true `
                        -AutoAddSignatureOnReply $true `
                        -ErrorAction Stop
                }}

                Disconnect-ExchangeOnline -Confirm:$false
                Write-Output "SUCCESS"
            }} catch {{
                Write-Error $_.Exception.Message
                exit 1
            }}
        """)

        return self._run_ps(script)

    # ─── Deploy em lote ───────────────────────────────────────────────────────

    def deploy_batch(self, items: list[dict]) -> list[dict]:
        """
        Deploya assinaturas para múltiplos usuários em uma única sessão
        do PowerShell (mais eficiente que abrir/fechar por usuário).

        items: [{"email": "...", "html": "..."}, ...]
        Retorna: [{"email": "...", "ok": bool, "msg": "..."}, ...]
        """
        ok, msg = self.is_configured()
        if not ok:
            return [{"email": i["email"], "ok": False, "msg": msg} for i in items]

        # Serializa os items em JSON para passar ao PowerShell
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                        delete=False, encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)
            json_path = f.name

        if self.cert_path and Path(self.cert_path).exists():
            connect_cmd = textwrap.dedent(f"""
                $SecurePass = ConvertTo-SecureString '{self.cert_password}' -AsPlainText -Force
                Connect-ExchangeOnline `
                    -AppId '{self.app_id}' `
                    -CertificateFilePath '{self.cert_path}' `
                    -CertificatePassword $SecurePass `
                    -Organization '{self.organization}' `
                    -ShowBanner:$false
            """)
        else:
            connect_cmd = textwrap.dedent(f"""
                Connect-ExchangeOnline `
                    -AppId '{self.app_id}' `
                    -CertificateThumbprint '{self.cert_thumb}' `
                    -Organization '{self.organization}' `
                    -ShowBanner:$false
            """)

        results_path = json_path.replace(".json", "_results.json")
        safe_signature_name = self.signature_name.replace("'", "''")

        script = textwrap.dedent(f"""
            $ErrorActionPreference = 'Continue'
            {connect_cmd}
            $signatureName = '{safe_signature_name}'
            $items   = Get-Content '{json_path}' | ConvertFrom-Json
            $results = @()
            foreach ($item in $items) {{
                try {{
                    $signatureHtml = [string]$item.html

                    try {{
                        # Exchange Online com roaming signatures (new Outlook/OWA).
                        Set-MailboxMessageConfiguration `
                            -Identity $item.email `
                            -SignatureName $signatureName `
                            -SignatureHtmlBody $signatureHtml `
                            -DefaultSignature $signatureName `
                            -DefaultSignatureOnReply $signatureName `
                            -DefaultFormat Html `
                            -AutoAddSignature $true `
                            -AutoAddSignatureOnReply $true `
                            -ErrorAction Stop
                    }} catch {{
                        # Fallback legado para tenants/cmdlets sem parâmetros de roaming.
                        Set-MailboxMessageConfiguration `
                            -Identity $item.email `
                            -SignatureHtml $signatureHtml `
                            -DefaultFormat Html `
                            -AutoAddSignature $true `
                            -AutoAddSignatureOnReply $true `
                            -ErrorAction Stop
                    }}

                    $results += [PSCustomObject]@{{ email=$item.email; ok=$true; msg="OK" }}
                }} catch {{
                    $results += [PSCustomObject]@{{ email=$item.email; ok=$false; msg=$_.Exception.Message }}
                }}
            }}
            Disconnect-ExchangeOnline -Confirm:$false
            $results | ConvertTo-Json -Depth 3 | Out-File '{results_path}' -Encoding utf8
        """)

        self._run_ps(script)

        results = []
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                raw = [raw]
            for r in raw:
                results.append({
                    "email": r.get("email", ""),
                    "ok":    bool(r.get("ok", False)),
                    "msg":   r.get("msg", ""),
                })
        except Exception as e:
            results = [{"email": i["email"], "ok": False, "msg": str(e)} for i in items]
        finally:
            for p in [json_path, results_path]:
                try:
                    os.unlink(p)
                except Exception:
                    pass

        return results

    # ─── Helpers internos ─────────────────────────────────────────────────────

    def _run_ps(self, script: str) -> tuple[bool, str]:
        """Executa um script PowerShell e retorna (sucesso, mensagem)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ps1",
                                        delete=False, encoding="utf-8") as f:
            f.write(script)
            script_path = f.name

        try:
            result = subprocess.run(
                ["pwsh", "-NonInteractive", "-File", script_path],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            else:
                err = result.stderr.strip() or result.stdout.strip()
                return False, err
        except subprocess.TimeoutExpired:
            return False, "Timeout ao executar PowerShell (>600s)"
        except FileNotFoundError:
            return False, "pwsh não encontrado. Instale o PowerShell Core."
        finally:
            try:
                os.unlink(script_path)
            except Exception:
                pass

    # ─── Utilitários ──────────────────────────────────────────────────────────

    def test_connection(self) -> tuple[bool, str]:
        """Testa a conexão com o Exchange Online."""
        ok, msg = self.is_configured()
        if not ok:
            return False, msg

        if self.cert_path and Path(self.cert_path).exists():
            connect_cmd = textwrap.dedent(f"""
                $SecurePass = ConvertTo-SecureString '{self.cert_password}' -AsPlainText -Force
                Connect-ExchangeOnline `
                    -AppId '{self.app_id}' `
                    -CertificateFilePath '{self.cert_path}' `
                    -CertificatePassword $SecurePass `
                    -Organization '{self.organization}' `
                    -ShowBanner:$false
            """)
        else:
            connect_cmd = textwrap.dedent(f"""
                Connect-ExchangeOnline `
                    -AppId '{self.app_id}' `
                    -CertificateThumbprint '{self.cert_thumb}' `
                    -Organization '{self.organization}' `
                    -ShowBanner:$false
            """)

        script = textwrap.dedent(f"""
            $ErrorActionPreference = 'Stop'
            try {{
                {connect_cmd}
                $org = Get-OrganizationConfig | Select-Object -ExpandProperty DisplayName
                Disconnect-ExchangeOnline -Confirm:$false
                Write-Output "Conectado: $org"
            }} catch {{
                Write-Error $_.Exception.Message
                exit 1
            }}
        """)
        return self._run_ps(script)

    @staticmethod
    def install_module_script() -> str:
        """Retorna o script PowerShell para instalar o módulo ExchangeOnlineManagement."""
        return textwrap.dedent("""
            if (-not (Get-Module -ListAvailable -Name ExchangeOnlineManagement)) {
                Install-Module -Name ExchangeOnlineManagement -Force -AllowClobber -Scope CurrentUser
                Write-Output "Módulo instalado com sucesso."
            } else {
                Write-Output "Módulo já instalado."
            }
        """)
