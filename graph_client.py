"""
graph_client.py — Microsoft Graph API
Busca usuários do Azure Active Directory usando autenticação por client credentials.
"""
import os
import requests
import msal
from dotenv import load_dotenv

load_dotenv()


class GraphClient:
    GRAPH_URL = "https://graph.microsoft.com/v1.0"
    SCOPE     = ["https://graph.microsoft.com/.default"]

    def __init__(self):
        self.tenant_id     = os.getenv("AZURE_TENANT_ID")
        self.client_id     = os.getenv("AZURE_CLIENT_ID")
        self.client_secret = os.getenv("AZURE_CLIENT_SECRET")

        if not all([self.tenant_id, self.client_id, self.client_secret]):
            raise ValueError(
                "Configure AZURE_TENANT_ID, AZURE_CLIENT_ID e AZURE_CLIENT_SECRET no .env"
            )

        self._token = None

    # ─── Auth ─────────────────────────────────────────────────────────────────

    def _get_token(self) -> str:
        app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
        )
        result = app.acquire_token_for_client(scopes=self.SCOPE)
        if "access_token" not in result:
            raise RuntimeError(
                f"Falha ao obter token do Azure AD: {result.get('error_description', result)}"
            )
        return result["access_token"]

    def _headers(self) -> dict:
        if not self._token:
            self._token = self._get_token()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type":  "application/json",
        }

    def _get(self, path: str, params: dict = None) -> dict:
        resp = requests.get(
            f"{self.GRAPH_URL}{path}",
            headers=self._headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    # ─── Users ────────────────────────────────────────────────────────────────

    def get_all_users(self) -> list[dict]:
        """
        Busca todos os usuários habilitados do Azure AD e retorna no
        formato esperado pelo database.upsert_employee().
        """
        fields = ",".join([
            "id", "displayName", "mail", "userPrincipalName",
            "jobTitle", "mobilePhone", "businessPhones",
            "department", "officeLocation", "companyName", "accountEnabled",
        ])

        # Suporta múltiplos domínios separados por vírgula
        # Ex: M365_DOMAINS=gtmalimentos.com.br,pescadosbemfresco.com.br
        domains_raw = os.getenv("M365_DOMAINS", os.getenv("M365_DOMAIN", ""))
        domains = [d.strip().lower() for d in domains_raw.split(",") if d.strip()]

        results = []
        url     = "/users"
        params  = {
            "$select": fields,
            "$filter": "accountEnabled eq true",
            "$top":    "999",
        }

        while url:
            data = self._get(url if url.startswith("/") else url.replace(self.GRAPH_URL, ""),
                             params=params)
            params = None  # Apenas na primeira requisição

            for u in data.get("value", []):
                email = u.get("mail") or u.get("userPrincipalName", "")
                if not email:
                    continue
                # Filtra por domínio(s) da empresa — pula contas de sistema
                email_lower = email.lower()
                if domains and not any(d in email_lower for d in domains):
                    continue

                phone = (u.get("mobilePhone") or
                         (u.get("businessPhones") or [""])[0] or "")
                company_name = (u.get("companyName") or "").strip()

                results.append({
                    "azure_id":   u.get("id", ""),
                    "email":      email,
                    "name":       u.get("displayName", ""),
                    "title":      u.get("jobTitle", ""),
                    "phone":      phone,
                    "department": u.get("department", ""),
                    "website":    os.getenv("VPS_BASE_URL", "").replace("assinaturas.", "www."),
                    "instagram":  "",
                    "extra2":     company_name,
                })

            # Paginação
            next_link = data.get("@odata.nextLink")
            url = next_link if next_link else None

        return results

    def get_user(self, user_id: str) -> dict | None:
        """Busca um usuário específico pelo ID ou email."""
        try:
            data = self._get(f"/users/{user_id}")
            return data
        except Exception:
            return None

    def test_connection(self) -> tuple[bool, str]:
        """Testa a conexão com o Azure AD."""
        try:
            data = self._get("/organization")
            org  = data.get("value", [{}])[0].get("displayName", "desconhecida")
            return True, f"Conectado à organização: {org}"
        except Exception as e:
            return False, str(e)
