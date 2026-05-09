"""
GTM Signature Agent
====================
Roda no PC de cada usuário (Windows). Detecta o e-mail da conta Outlook,
baixa a assinatura mais recente da VPS, e escreve nos lugares onde Outlook
clássico e novo Outlook procuram assinatura. Reporta heartbeat para a VPS.

Uso (manual, pra teste):
    python gtm_signature_agent.py

Empacotamento (Phase 2):
    pyinstaller --onefile --noconsole gtm_signature_agent.py

Agendamento:
    Tarefa Agendada do Windows: dispara no logon + diariamente às 10h.
"""
import json
import logging
import os
import platform
import re
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

AGENT_VERSION = "0.2.0"
VPS_BASE = os.environ.get("GTM_VPS_BASE", "https://assinatura.gtmalimentos.com.br")
DOMAINS = ("@gtmalimentos.com.br", "@pescadosbemfresco.com.br")
SIG_NAME = "GTM Assinatura"

LOG_DIR = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "GTMSignatureAgent"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "agent.log"

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("gtm-agent")


# ─── Detecção do e-mail do usuário ────────────────────────────────────────────

def detect_email_from_env():
    """Tenta variáveis de ambiente típicas em PCs Azure AD-joined."""
    for var in ("USERPRINCIPALNAME", "USERPRINCIPAL", "EMAIL"):
        v = os.environ.get(var, "").strip().lower()
        if v and any(d in v for d in DOMAINS):
            return v
    return None


def detect_email_from_outlook_registry():
    """Lê o profile do Outlook no registry pra extrair o e-mail SMTP primário.
    Funciona pro Outlook clássico (chave estável)."""
    try:
        import winreg
    except ImportError:
        return None

    candidates = []
    for ver in ("16.0", "15.0"):
        for hive_name in ("HKEY_CURRENT_USER",):
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    rf"Software\Microsoft\Office\{ver}\Outlook\Profiles",
                ) as profiles_key:
                    n_profiles, _, _ = winreg.QueryInfoKey(profiles_key)
                    for i in range(n_profiles):
                        profile_name = winreg.EnumKey(profiles_key, i)
                        # Cada profile tem subchaves; varremos procurando "IMAP"/"SMTP" Primary
                        try:
                            _walk_profile_for_email(
                                winreg, profiles_key, profile_name, candidates)
                        except Exception as e:
                            log.debug("walk profile %s: %s", profile_name, e)
            except FileNotFoundError:
                continue
            except Exception as e:
                log.debug("open profiles: %s", e)
                continue

    for c in candidates:
        if any(d in c for d in DOMAINS):
            return c
    return None


def _walk_profile_for_email(winreg, profiles_key, profile_name, out):
    """Caminha recursivamente em subchaves de um profile coletando strings que
    pareçam e-mail de domínios alvo."""
    EMAIL_RE = re.compile(rb"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
    queue = [profile_name]
    visited = set()
    while queue:
        path = queue.pop(0)
        if path in visited:
            continue
        visited.add(path)
        try:
            with winreg.OpenKey(profiles_key, path) as k:
                n_sub, n_val, _ = winreg.QueryInfoKey(k)
                for i in range(n_val):
                    name, value, vtype = winreg.EnumValue(k, i)
                    raw = value if isinstance(value, bytes) else (
                        str(value).encode("utf-8", "ignore"))
                    for m in EMAIL_RE.finditer(raw):
                        addr = m.group(1).decode("utf-8", "ignore").lower()
                        if any(d in addr for d in DOMAINS):
                            out.append(addr)
                for i in range(n_sub):
                    sub = winreg.EnumKey(k, i)
                    queue.append(f"{path}\\{sub}")
        except Exception:
            continue


def detect_email_from_args():
    """Permite passar o e-mail por argumento (útil em teste e no MSI installer
    que passa o e-mail no agendamento da tarefa)."""
    for i, arg in enumerate(sys.argv[1:]):
        if arg.startswith("--email="):
            return arg.split("=", 1)[1].strip().lower()
        if arg == "--email" and i + 2 <= len(sys.argv):
            return sys.argv[i + 2].strip().lower()
    return None


def detect_email_from_whoami():
    """`whoami /upn` retorna o User Principal Name em PCs Azure AD-joined
    ou domain-joined — tipicamente já é o e-mail corporativo."""
    try:
        import subprocess
        r = subprocess.run(
            ["whoami", "/upn"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        v = (r.stdout or "").strip().lower()
        if v and any(d in v for d in DOMAINS):
            return v
    except Exception as e:
        log.debug("whoami /upn falhou: %s", e)
    return None


def detect_email_from_explicit_env():
    """Variável dedicada que o instalador MSI vai setar."""
    v = os.environ.get("GTM_USER_EMAIL", "").strip().lower()
    return v if v else None


def detect_email():
    email = detect_email_from_args()
    if email:
        log.info("e-mail recebido por argumento: %s", email)
        return email
    email = detect_email_from_explicit_env()
    if email:
        log.info("e-mail via GTM_USER_EMAIL: %s", email)
        return email
    email = detect_email_from_whoami()
    if email:
        log.info("e-mail via whoami /upn: %s", email)
        return email
    email = detect_email_from_env()
    if email:
        log.info("e-mail detectado via env: %s", email)
        return email
    email = detect_email_from_outlook_registry()
    if email:
        log.info("e-mail detectado via registry Outlook: %s", email)
        return email
    log.warning("não foi possível detectar e-mail do usuário")
    return None


# ─── Comunicação com a VPS ────────────────────────────────────────────────────

def fetch_signature(email):
    url = f"{VPS_BASE}/api/agent/signature?email={email}"
    log.info("GET %s", url)
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_image(image_url, dest_path):
    log.info("baixando imagem: %s", image_url)
    urllib.request.urlretrieve(image_url, dest_path)


def post_heartbeat(payload):
    url = f"{VPS_BASE}/api/agent/heartbeat"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        log.info("heartbeat enviado: %s", payload.get("status"))
    except Exception as e:
        log.warning("heartbeat falhou: %s", e)


# ─── Escrita da assinatura no Outlook ─────────────────────────────────────────

def write_outlook_classic(html, image_url):
    """Escreve a assinatura nos arquivos que o Outlook clássico lê."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA não definido")

    sig_dir = Path(appdata) / "Microsoft" / "Signatures"
    sig_dir.mkdir(parents=True, exist_ok=True)

    files_dir = sig_dir / f"{SIG_NAME}_arquivos"
    files_dir.mkdir(exist_ok=True)

    # Baixa a imagem pra pasta local
    img_local = files_dir / "image001.png"
    fetch_image(image_url, img_local)

    # Substitui URL remota pela referência local relativa (Outlook precisa assim)
    rel_img = f"{SIG_NAME}_arquivos/image001.png"
    local_html = html.replace(image_url, rel_img)

    # 3 arquivos esperados pelo Outlook
    htm_path = sig_dir / f"{SIG_NAME}.htm"
    txt_path = sig_dir / f"{SIG_NAME}.txt"
    rtf_path = sig_dir / f"{SIG_NAME}.rtf"

    htm_path.write_text(local_html, encoding="utf-8")
    txt_path.write_text("", encoding="utf-8")  # versão texto vazia
    # RTF mínimo (Outlook desktop fallback)
    rtf_path.write_text(r"{\rtf1\ansi\deff0 {\fonttbl{\f0 Arial;}}\f0\fs20}",
                        encoding="latin-1")

    log.info("arquivos de assinatura escritos em %s", sig_dir)
    return str(sig_dir)


def set_outlook_default_signature():
    """Define a assinatura como padrão pra novos e-mails e respostas no
    Outlook clássico via registry. Funciona por conta no profile."""
    try:
        import winreg
    except ImportError:
        log.info("winreg indisponível — pulando registry")
        return

    for ver in ("16.0", "15.0"):
        try:
            base = rf"Software\Microsoft\Office\{ver}\Common\MailSettings"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
                winreg.SetValueEx(k, "NewSignature", 0, winreg.REG_SZ, SIG_NAME)
                winreg.SetValueEx(k, "ReplySignature", 0, winreg.REG_SZ, SIG_NAME)
            log.info("registry MailSettings %s atualizado", ver)
        except Exception as e:
            log.debug("registry %s falhou: %s", ver, e)


def set_outlook_per_account_signature(email):
    """Tenta setar a assinatura por conta no profile do Outlook
    (Outlook 2016+). Best-effort — algumas chaves estão criptografadas."""
    try:
        import winreg
    except ImportError:
        return

    for ver in ("16.0", "15.0"):
        try:
            base = rf"Software\Microsoft\Office\{ver}\Outlook\Profiles"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base) as profiles:
                n_profiles, _, _ = winreg.QueryInfoKey(profiles)
                for i in range(n_profiles):
                    profile = winreg.EnumKey(profiles, i)
                    try:
                        accounts_path = rf"{profile}\9375CFF0413111d3B88A00104B2A6676"
                        with winreg.OpenKey(profiles, accounts_path) as accounts:
                            n_acc, _, _ = winreg.QueryInfoKey(accounts)
                            for j in range(n_acc):
                                acc_id = winreg.EnumKey(accounts, j)
                                acc_full = rf"{accounts_path}\{acc_id}"
                                with winreg.OpenKey(profiles, acc_full,
                                                    0, winreg.KEY_SET_VALUE) as acc_key:
                                    winreg.SetValueEx(acc_key, "New Signature",
                                                      0, winreg.REG_SZ, SIG_NAME)
                                    winreg.SetValueEx(acc_key, "Reply-Forward Signature",
                                                      0, winreg.REG_SZ, SIG_NAME)
                                log.info("assinatura por conta setada em %s", acc_full)
                    except FileNotFoundError:
                        continue
                    except Exception as e:
                        log.debug("per-account %s: %s", profile, e)
        except FileNotFoundError:
            continue


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("GTM Signature Agent v%s iniciando", AGENT_VERSION)

    hostname = socket.gethostname()
    os_ver = f"{platform.system()} {platform.release()} {platform.version()}"

    email = detect_email()
    if not email:
        msg = "e-mail do usuário não detectado"
        log.error(msg)
        post_heartbeat({
            "email": "", "hostname": hostname, "os_version": os_ver,
            "agent_version": AGENT_VERSION, "signature_version": "",
            "status": "error", "error": msg,
        })
        sys.exit(2)

    try:
        sig = fetch_signature(email)
    except urllib.error.HTTPError as e:
        msg = f"VPS retornou {e.code}: {e.reason}"
        log.error(msg)
        post_heartbeat({
            "email": email, "hostname": hostname, "os_version": os_ver,
            "agent_version": AGENT_VERSION, "signature_version": "",
            "status": "error", "error": msg,
        })
        sys.exit(3)
    except Exception as e:
        msg = f"falha ao buscar assinatura: {e}"
        log.error(msg)
        post_heartbeat({
            "email": email, "hostname": hostname, "os_version": os_ver,
            "agent_version": AGENT_VERSION, "signature_version": "",
            "status": "error", "error": msg,
        })
        sys.exit(4)

    try:
        write_outlook_classic(sig["html"], sig["image_url"])
        set_outlook_default_signature()
        set_outlook_per_account_signature(email)
    except Exception as e:
        msg = f"falha ao escrever assinatura: {e}"
        log.exception(msg)
        post_heartbeat({
            "email": email, "hostname": hostname, "os_version": os_ver,
            "agent_version": AGENT_VERSION,
            "signature_version": sig.get("version", ""),
            "status": "error", "error": msg,
        })
        sys.exit(5)

    post_heartbeat({
        "email": email, "hostname": hostname, "os_version": os_ver,
        "agent_version": AGENT_VERSION,
        "signature_version": sig.get("version", ""),
        "status": "ok", "error": "",
    })
    log.info("sync concluído com sucesso para %s", email)


if __name__ == "__main__":
    main()
