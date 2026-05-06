"""
app.py — GTM Signature App
Aplicação Flask para geração e deploy automático de assinaturas de email.
"""
import os
import json
import uuid
from pathlib import Path
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, send_from_directory, flash
)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

import database as db
from graph_client import GraphClient
from image_generator import SignatureGenerator
from signature_deployer import SignatureDeployer

# ─── Setup ────────────────────────────────────────────────────────────────────

load_dotenv()

BASE_DIR   = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
SIG_DIR    = BASE_DIR / "static" / "signatures"
FONT_DIR   = BASE_DIR / "fonts"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
SIG_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

db.init_db()

# Filtro Jinja2 para parsear JSON dentro dos templates
@app.template_filter("from_json")
def from_json_filter(value):
    try:
        return json.loads(value)
    except Exception:
        return []


# ─── Auth ─────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd == os.getenv("ADMIN_PASSWORD", "admin123"):
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        error = "Senha incorreta."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    stats   = db.get_stats()
    layouts = db.get_all_layouts()
    active  = db.get_active_layout()
    log     = db.get_deploy_log(limit=10)
    return render_template("dashboard.html",
                           stats=stats, layouts=layouts,
                           active_layout=active, log=log)


# ─── Layouts / Upload ─────────────────────────────────────────────────────────

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/layouts")
@login_required
def layouts():
    all_layouts = db.get_all_layouts()
    active      = db.get_active_layout()
    return render_template("layouts.html", layouts=all_layouts, active_layout=active)


@app.route("/layouts/upload", methods=["GET", "POST"])
@login_required
def upload_layout():
    if request.method == "POST":
        name = request.form.get("name", "Layout sem nome")
        file = request.files.get("image")
        if not file or not allowed_file(file.filename):
            flash("Envie uma imagem PNG ou JPG válida.", "error")
            return redirect(request.url)
        ext      = file.filename.rsplit(".", 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        file.save(UPLOAD_DIR / filename)
        layout_id = db.save_layout(name, filename, [])
        flash("Layout criado! Agora posicione os campos.", "success")
        return redirect(url_for("editor", layout_id=layout_id))
    return render_template("upload.html")


@app.route("/layouts/<int:layout_id>/activate", methods=["POST"])
@login_required
def activate_layout(layout_id):
    db.set_active_layout(layout_id)
    flash("Layout ativado com sucesso!", "success")
    return redirect(url_for("layouts"))


@app.route("/layouts/<int:layout_id>/delete", methods=["POST"])
@login_required
def delete_layout(layout_id):
    # Apenas remove do banco; não apaga a imagem física
    conn = db.get_db()
    conn.execute("DELETE FROM layouts WHERE id=?", (layout_id,))
    conn.commit()
    conn.close()
    flash("Layout removido.", "info")
    return redirect(url_for("layouts"))


# ─── Editor visual ───────────────────────────────────────────────────────────

@app.route("/editor/<int:layout_id>")
@login_required
def editor(layout_id):
    layout = db.get_layout(layout_id)
    if not layout:
        flash("Layout não encontrado.", "error")
        return redirect(url_for("layouts"))
    return render_template("editor.html", layout=layout)


@app.route("/api/layout/<int:layout_id>/save", methods=["POST"])
@login_required
def save_layout_fields(layout_id):
    data   = request.get_json()
    fields = data.get("fields", [])
    db.update_layout_fields(layout_id, fields)
    return jsonify({"ok": True})


@app.route("/api/layout/<int:layout_id>")
@login_required
def get_layout_api(layout_id):
    layout = db.get_layout(layout_id)
    if not layout:
        return jsonify({"error": "not found"}), 404
    return jsonify(layout)


# ─── Funcionários ─────────────────────────────────────────────────────────────

@app.route("/employees")
@login_required
def employees():
    emps = db.get_all_employees()
    return render_template("employees.html", employees=emps)


@app.route("/employees/<int:emp_id>/edit", methods=["GET", "POST"])
@login_required
def edit_employee(emp_id):
    emp = db.get_employee(emp_id)
    if not emp:
        flash("Funcionário não encontrado.", "error")
        return redirect(url_for("employees"))
    if request.method == "POST":
        db.update_employee(emp_id, {
            "name":       request.form.get("name", ""),
            "title":      request.form.get("title", ""),
            "phone":      request.form.get("phone", ""),
            "department": request.form.get("department", ""),
            "website":    request.form.get("website", ""),
            "instagram":  request.form.get("instagram", ""),
            "extra1":     request.form.get("extra1", ""),
            "extra2":     request.form.get("extra2", ""),
        })
        flash("Dados atualizados!", "success")
        return redirect(url_for("employees"))
    return render_template("edit_employee.html", emp=emp)


@app.route("/employees/sync", methods=["POST"])
@login_required
def sync_employees():
    try:
        client = GraphClient()
        users  = client.get_all_users()
        count  = 0
        for u in users:
            db.upsert_employee(u)
            count += 1
        flash(f"{count} funcionário(s) sincronizados do Azure AD.", "success")
    except Exception as e:
        flash(f"Erro ao sincronizar: {e}", "error")
    return redirect(url_for("employees"))


@app.route("/employees/add", methods=["GET", "POST"])
@login_required
def add_employee():
    if request.method == "POST":
        db.upsert_employee({
            "azure_id":   "",
            "email":      request.form.get("email", ""),
            "name":       request.form.get("name", ""),
            "title":      request.form.get("title", ""),
            "phone":      request.form.get("phone", ""),
            "department": request.form.get("department", ""),
            "website":    request.form.get("website", ""),
            "instagram":  request.form.get("instagram", ""),
        })
        flash("Funcionário adicionado!", "success")
        return redirect(url_for("employees"))
    return render_template("add_employee.html")


# ─── Geração de imagens ───────────────────────────────────────────────────────

@app.route("/generate", methods=["GET", "POST"])
@login_required
def generate():
    active = db.get_active_layout()
    emps   = db.get_all_employees()
    results = []

    if request.method == "POST":
        if not active:
            flash("Nenhum layout ativo. Ative um layout primeiro.", "error")
            return redirect(url_for("layouts"))

        selected_ids = request.form.getlist("emp_ids")
        if not selected_ids:
            # Gerar todos
            targets = emps
        else:
            targets = [e for e in emps if str(e["id"]) in selected_ids]

        generator = SignatureGenerator(
            base_image_path=str(UPLOAD_DIR / active["base_image"]),
            fields=active["fields"],
            output_dir=str(SIG_DIR),
            font_dir=str(FONT_DIR),
            target_width=0,  # 0 = mantém resolução original sem redimensionar
        )

        for emp in targets:
            try:
                filename = generator.generate(emp)
                db.set_employee_image(emp["id"], filename)
                results.append({"email": emp["email"], "ok": True, "file": filename})
            except Exception as e:
                results.append({"email": emp["email"], "ok": False, "error": str(e)})

        ok_count = sum(1 for r in results if r["ok"])
        flash(f"{ok_count}/{len(results)} imagens geradas com sucesso.", "success")

    return render_template("generate.html", active_layout=active, employees=emps, results=results)


@app.route("/api/generate/<int:emp_id>", methods=["POST"])
@login_required
def generate_one(emp_id):
    active = db.get_active_layout()
    emp    = db.get_employee(emp_id)
    if not active or not emp:
        return jsonify({"ok": False, "error": "Layout ou funcionário não encontrado"})
    try:
        generator = SignatureGenerator(
            base_image_path=str(UPLOAD_DIR / active["base_image"]),
            fields=active["fields"],
            output_dir=str(SIG_DIR),
            font_dir=str(FONT_DIR),
            target_width=0,  # 0 = mantém resolução original sem redimensionar
        )
        filename = generator.generate(emp)
        db.set_employee_image(emp_id, filename)
        return jsonify({"ok": True, "file": filename})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ─── Deploy M365 ──────────────────────────────────────────────────────────────

@app.route("/deploy", methods=["GET", "POST"])
@login_required
def deploy():
    emps    = db.get_all_employees()
    results = []

    if request.method == "POST":
        selected_ids = request.form.getlist("emp_ids")
        targets = [e for e in emps if str(e["id"]) in selected_ids] if selected_ids else [e for e in emps if e["img_path"]]

        vps_url    = os.getenv("VPS_BASE_URL", "").rstrip("/")
        deployer   = SignatureDeployer()

        for emp in targets:
            if not emp.get("img_path"):
                results.append({"email": emp["email"], "ok": False, "error": "Imagem não gerada"})
                continue
            img_url  = f"{vps_url}/static/signatures/{emp['img_path']}"
            sig_html = _build_signature_html(emp, img_url)
            ok, msg  = deployer.deploy(emp["email"], sig_html)
            db.set_employee_deployed(emp["id"], ok)
            db.log_deploy(emp["id"], emp["email"], "ok" if ok else "error", msg)
            results.append({"email": emp["email"], "ok": ok, "error": msg if not ok else ""})

        ok_count = sum(1 for r in results if r["ok"])
        flash(f"{ok_count}/{len(results)} assinaturas deployadas.", "success")

    return render_template("deploy.html", employees=emps, results=results)


def _build_signature_html(emp, img_url):
    """Gera o HTML da assinatura com a imagem hospedada na VPS."""
    email = emp.get("email", "")
    # width="600" como atributo HTML é essencial para o Outlook respeitar o tamanho
    return f"""<div style="font-family:Arial,sans-serif;font-size:0;line-height:0;">
  <a href="mailto:{email}" style="border:none;text-decoration:none;">
    <img src="{img_url}" alt="Assinatura {emp.get('name','')}"
         width="600"
         style="width:600px;max-width:100%;border:none;display:block;" />
  </a>
</div>"""


# ─── Servir fontes customizadas ───────────────────────────────────────────────

@app.route("/fonts/<path:filename>")
def serve_font(filename):
    return send_from_directory(str(FONT_DIR), filename)


# ─── Servir imagens de assinatura ─────────────────────────────────────────────

@app.route("/static/signatures/<path:filename>")
def serve_signature(filename):
    resp = send_from_directory(str(SIG_DIR), filename)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"]        = "no-cache"
    resp.headers["Expires"]       = "0"
    return resp


@app.route("/static/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(str(UPLOAD_DIR), filename)


# ─── Rota dinâmica para Transport Rule do Exchange ────────────────────────────
# Uso na regra: <img src="http://82.29.62.7:5001/sig/%%WindowsEmailAddress%%">
# O Exchange substitui %%WindowsEmailAddress%% pelo email real do remetente

@app.route("/sig/")
@app.route("/sig/<path:email>")
def sig_by_email(email=""):
    """Serve a imagem de assinatura pelo endereço de email (sem autenticação).
    Usado na Transport Rule do Exchange Online com %%WindowsEmailAddress%%."""
    import re
    from urllib.parse import unquote
    # Decodifica URL encoding (%40 → @) e normaliza
    email = unquote(email).lower().strip()
    safe  = re.sub(r"[^a-z0-9]", "_", email)
    img_path = SIG_DIR / f"{safe}.png"
    if img_path.exists():
        resp = send_from_directory(str(SIG_DIR), f"{safe}.png")
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"]        = "no-cache"
        resp.headers["Expires"]       = "0"
        return resp
    # Fallback: retorna imagem padrão se funcionário não tiver assinatura gerada
    fallback = SIG_DIR / "default.png"
    if fallback.exists():
        return send_from_directory(str(SIG_DIR), "default.png")
    return "", 204  # Sem conteúdo — email sai sem assinatura


# ─── API preview ──────────────────────────────────────────────────────────────

@app.route("/api/preview/<int:emp_id>")
@login_required
def preview_signature(emp_id):
    emp = db.get_employee(emp_id)
    if not emp or not emp.get("img_path"):
        return "Imagem não gerada", 404
    # Usa URL relativa para funcionar com IP + porta sem precisar de domínio
    img_url = f"/static/signatures/{emp['img_path']}"
    name    = emp.get("name", "")
    return f"""<!doctype html><html><body style="margin:0;background:#f5f5f5;padding:20px;">
    <p style="font-family:sans-serif;color:#555;margin-bottom:12px;">Preview: <strong>{name}</strong></p>
    <img src="{img_url}" style="max-width:700px;box-shadow:0 2px 12px rgba(0,0,0,.2);display:block;">
    <p style="font-family:sans-serif;font-size:12px;color:#999;margin-top:8px;">URL da imagem: <code>http://82.29.62.7:5001{img_url}</code></p>
    </body></html>"""


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("APP_PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
