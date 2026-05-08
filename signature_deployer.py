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
import re
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
        self.app_id        = os.getenv("EXCHANGE_APP_ID", "")
        self.cert_thumb    = os.getenv("EXCHANGE_CERT_THUMBPRINT", "")
        self.organization  = os.getenv("EXCHANGE_ORGANIZATION", "")
        self.cert_path     = os.getenv("EXCHANGE_CERT_PATH", "")      # .pfx opcional
        self.cert_password = os.getenv("EXCHANGE_CERT_PASSWORD", "")  # senha do .pfx
        self.signature_name = os.getenv("EXCHANGE_SIGNATURE_NAME", "GTM Assinatura")
        self._ps_available = self._check_powershell()

    ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

    @classmethod
    def _sanitize_powershell_output(cls, text: str) -> str:
        """Remove códigos ANSI e ruído comum do output do PowerShell."""
        if not text:
            return ""

        cleaned = cls.ANSI_ESCAPE_RE.sub("", text).replace("\r", "")
        lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]

        filtered = []
        for ln in lines:
            # Mantém apenas mensagens úteis para o usuário.
            if re.match(r"^/tmp/.*\.ps1:\d+", ln):
                continue
            if re.match(r"^Line\s+\|", ln):
                continue
            if re.match(r"^\d+\s+\|", ln):
                continue
            if ln.startswith("+ CategoryInfo"):
                continue
            if ln.startswith("+ FullyQualifiedErrorId"):
                continue
            if ln == "Write-Error:":
                continue
            filtered.append(ln)

        merged = " | ".join(filtered).strip()
        if "ERROR::" in merged:
            merged = merged.split("ERROR::", 1)[1].strip()
        return merged or "Falha ao executar comando do Exchange Online."

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
        if self.cert_path and not Path(self.cert_path).exists():
            return False, f"EXCHANGE_CERT_PATH não encontrado: {self.cert_path}"
        if not self.organization:
            return False, "EXCHANGE_ORGANIZATION não configurado no .env"
        return True, "OK"

    def _build_connect_command(self) -> str:
        """Monta o comando de conexão CBA no Exchange com fallback seguro."""
        app_id = (self.app_id or "").replace("'", "''")
        cert_thumb = (self.cert_thumb or "").replace("'", "''")
        organization = (self.organization or "").replace("'", "''")
        cert_path = (self.cert_path or "").replace("'", "''")
        cert_password = (self.cert_password or "").replace("'", "''")

        return textwrap.dedent(f"""
            $exoCmd = Get-Command Connect-ExchangeOnline -ErrorAction Stop
            $hasThumbprint = $exoCmd.Parameters.ContainsKey('CertificateThumbprint')
            $hasCertFile   = $exoCmd.Parameters.ContainsKey('CertificateFilePath')
            $certPath      = '{cert_path}'
            $thumbprint    = '{cert_thumb}'

            if ($certPath -and (Test-Path $certPath) -and $hasCertFile) {{
                $SecurePass = ConvertTo-SecureString '{cert_password}' -AsPlainText -Force
                Connect-ExchangeOnline `
                    -AppId '{app_id}' `
                    -CertificateFilePath $certPath `
                    -CertificatePassword $SecurePass `
                    -Organization '{organization}' `
                    -ShowBanner:$false
            }} elseif ($thumbprint -and $hasThumbprint) {{
                Connect-ExchangeOnline `
                    -AppId '{app_id}' `
                    -CertificateThumbprint $thumbprint `
                    -Organization '{organization}' `
                    -ShowBanner:$false
            }} elseif ($certPath -and -not (Test-Path $certPath)) {{
                throw "EXCHANGE_CERT_PATH não encontrado: $certPath"
            }} elseif ($thumbprint -and -not $hasThumbprint) {{
                throw "Seu módulo ExchangeOnlineManagement não suporta -CertificateThumbprint neste ambiente. Configure EXCHANGE_CERT_PATH e EXCHANGE_CERT_PASSWORD no .env."
            }} else {{
                throw "Nenhum método de certificado válido encontrado. Configure EXCHANGE_CERT_PATH+EXCHANGE_CERT_PASSWORD ou EXCHANGE_CERT_THUMBPRINT no .env."
            }}
        """)

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
        connect_cmd = self._build_connect_command()

        script = textwrap.dedent(f"""
            $ErrorActionPreference = 'Stop'
            $ProgressPreference = 'SilentlyContinue'
            if ($PSVersionTable.PSVersion.Major -ge 7) {{
                $PSStyle.OutputRendering = 'PlainText'
            }}
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
                    $roamingErr = $_.Exception.Message
                    # Fallback legado para tenants/cmdlets sem parâmetros de roaming.
                    try {{
                        Set-MailboxMessageConfiguration `
                            -Identity '{email}' `
                            -SignatureHtml $signatureHtml `
                            -DefaultFormat Html `
                            -AutoAddSignature $true `
                            -AutoAddSignatureOnReply $true `
                            -ErrorAction Stop
                    }} catch {{
                        $legacyErr = $_.Exception.Message
                        throw "Falha nos dois modos. Roaming: $roamingErr | Legado: $legacyErr"
                    }}
                }}

                Disconnect-ExchangeOnline -Confirm:$false
                Write-Output "SUCCESS"
            }} catch {{
                Write-Output ("ERROR::" + $_.Exception.Message)
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

        connect_cmd = self._build_connect_command()

        results_path = json_path.replace(".json", "_results.json")
        safe_signature_name = self.signature_name.replace("'", "''")

        script = textwrap.dedent(f"""
            $ErrorActionPreference = 'Continue'
            $ProgressPreference = 'SilentlyContinue'
            if ($PSVersionTable.PSVersion.Major -ge 7) {{
                $PSStyle.OutputRendering = 'PlainText'
            }}
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
                        $roamingErr = $_.Exception.Message
                        # Fallback legado para tenants/cmdlets sem parâmetros de roaming.
                        try {{
                            Set-MailboxMessageConfiguration `
                                -Identity $item.email `
                                -SignatureHtml $signatureHtml `
                                -DefaultFormat Html `
                                -AutoAddSignature $true `
                                -AutoAddSignatureOnReply $true `
                                -ErrorAction Stop
                        }} catch {{
                            $legacyErr = $_.Exception.Message
                            throw "Falha nos dois modos. Roaming: $roamingErr | Legado: $legacyErr"
                        }}
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
                ["pwsh", "-NoProfile", "-NonInteractive", "-File", script_path],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode == 0:
                return True, self._sanitize_powershell_output(result.stdout)
            else:
                err = result.stderr.strip() or result.stdout.strip()
                return False, self._sanitize_powershell_output(err)
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

        connect_cmd = self._build_connect_command()

        script = textwrap.dedent(f"""
            $ErrorActionPreference = 'Stop'
            $ProgressPreference = 'SilentlyContinue'
            if ($PSVersionTable.PSVersion.Major -ge 7) {{
                $PSStyle.OutputRendering = 'PlainText'
            }}
            try {{
                {connect_cmd}
                $org = Get-OrganizationConfig | Select-Object -ExpandProperty DisplayName
                Disconnect-ExchangeOnline -Confirm:$false
                Write-Output "Conectado: $org"
            }} catch {{
                Write-Output ("ERROR::" + $_.Exception.Message)
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
