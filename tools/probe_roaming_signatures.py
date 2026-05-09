"""
probe_roaming_signatures.py — Reconhecimento empírico do que o Graph API
permite fazer com Roaming Signatures em modo app-only.

Uso na VPS:
    cd /root/gtm-signature-app
    python3 tools/probe_roaming_signatures.py ti@gtmalimentos.com.br

Saída esperada: lista os endpoints que respondem 200/201 e os que falham,
com o body de erro para diagnóstico.
"""
import json
import sys
from pathlib import Path

# Permite rodar de qualquer diretório
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests
from graph_client import GraphClient


CANDIDATE_HTML = (
    "<!-- GTM_SIG_PROBE -->"
    "<p>Probe signature - se você está vendo isso no editor, deu certo.</p>"
)


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def try_request(method, url, headers, body=None):
    print(f"\n→ {method} {url}")
    if body is not None:
        print(f"  body: {json.dumps(body)[:200]}")
    try:
        r = requests.request(method, url, headers=headers,
                             json=body, timeout=30)
        print(f"  status: {r.status_code}")
        try:
            print(f"  resp:   {json.dumps(r.json(), indent=2)[:1500]}")
        except Exception:
            print(f"  resp:   {r.text[:1500]}")
        return r
    except Exception as e:
        print(f"  ERRO: {e}")
        return None


def main():
    if len(sys.argv) < 2:
        print("Uso: python3 probe_roaming_signatures.py <email>")
        sys.exit(1)

    email = sys.argv[1]
    gc = GraphClient()
    token = gc._get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    section(f"1) Listar mailboxSettings completo de {email} (v1.0)")
    try_request("GET",
        f"https://graph.microsoft.com/v1.0/users/{email}/mailboxSettings",
        headers)

    section(f"2) Listar mailboxSettings completo de {email} (beta)")
    try_request("GET",
        f"https://graph.microsoft.com/beta/users/{email}/mailboxSettings",
        headers)

    section(f"3) Tentar GET em endpoints suspeitos de roaming signatures")
    suspects = [
        f"https://graph.microsoft.com/beta/users/{email}/mailboxSettings/signatures",
        f"https://graph.microsoft.com/beta/users/{email}/mailboxSettings/roamingSignatures",
        f"https://graph.microsoft.com/beta/users/{email}/outlook/masterCategories",
        f"https://graph.microsoft.com/beta/users/{email}/messageRules",
        f"https://graph.microsoft.com/beta/users/{email}/signatures",
        f"https://graph.microsoft.com/beta/users/{email}/outlook/signatures",
    ]
    for url in suspects:
        try_request("GET", url, headers)

    section(f"4) Tentar PATCH em mailboxSettings com campo signature (beta)")
    try_request("PATCH",
        f"https://graph.microsoft.com/beta/users/{email}/mailboxSettings",
        headers,
        body={"signature": CANDIDATE_HTML})

    section(f"5) Tentar PATCH em mailboxSettings com roamingSignatures (beta)")
    try_request("PATCH",
        f"https://graph.microsoft.com/beta/users/{email}/mailboxSettings",
        headers,
        body={"roamingSignatures": [{
            "name": "GTM Assinatura",
            "isDefault": True,
            "htmlBody": CANDIDATE_HTML,
        }]})

    section(f"6) Tentar POST em /signatures (beta)")
    try_request("POST",
        f"https://graph.microsoft.com/beta/users/{email}/signatures",
        headers,
        body={
            "name": "GTM Assinatura",
            "isDefault": True,
            "htmlBody": CANDIDATE_HTML,
        })

    section("FIM")
    print("\nLeia os status codes acima:")
    print("- 200/201 em algum POST/PATCH = caminho viável, me avise qual")
    print("- 403 em todos = permissão MailboxSettings.ReadWrite falta no app")
    print("- 404 em todos = endpoint não existe nessa versão do Graph")


if __name__ == "__main__":
    main()
