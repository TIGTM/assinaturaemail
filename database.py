"""
database.py — SQLite helper
Gerencia employees, layouts e configurações da aplicação.
"""
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS employees (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            azure_id    TEXT UNIQUE,
            email       TEXT UNIQUE NOT NULL,
            name        TEXT,
            title       TEXT,
            phone       TEXT,
            department  TEXT,
            website     TEXT,
            instagram   TEXT,
            extra1      TEXT,
            extra2      TEXT,
            img_path    TEXT,
            img_updated TEXT,
            sig_deployed INTEGER DEFAULT 0,
            active      INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS layouts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            base_image  TEXT NOT NULL,
            fields_json TEXT NOT NULL,
            is_active   INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS deploy_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER,
            email       TEXT,
            status      TEXT,
            message     TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)

    conn.commit()
    conn.close()


# ─── Employees ────────────────────────────────────────────────────────────────

def upsert_employee(data: dict):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO employees (azure_id, email, name, title, phone, department, website, instagram)
        VALUES (:azure_id, :email, :name, :title, :phone, :department, :website, :instagram)
        ON CONFLICT(email) DO UPDATE SET
            azure_id    = excluded.azure_id,
            name        = excluded.name,
            title       = excluded.title,
            phone       = excluded.phone,
            department  = excluded.department,
            website     = excluded.website,
            instagram   = excluded.instagram,
            active      = 1,
            updated_at  = datetime('now')
    """, {
        "azure_id":   data.get("azure_id", ""),
        "email":      data["email"],
        "name":       data.get("name", ""),
        "title":      data.get("title", ""),
        "phone":      data.get("phone", ""),
        "department": data.get("department", ""),
        "website":    data.get("website", ""),
        "instagram":  data.get("instagram", ""),
    })
    conn.commit()
    conn.close()


def get_all_employees(active_only=True):
    conn = get_db()
    cur = conn.cursor()
    if active_only:
        cur.execute("SELECT * FROM employees WHERE active=1 ORDER BY name")
    else:
        cur.execute("SELECT * FROM employees ORDER BY name")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_employee(emp_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM employees WHERE id=?", (emp_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_employee(emp_id, data: dict):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE employees SET
            name=:name, title=:title, phone=:phone,
            department=:department, website=:website,
            instagram=:instagram, extra1=:extra1, extra2=:extra2,
            updated_at=datetime('now')
        WHERE id=:id
    """, {**data, "id": emp_id})
    conn.commit()
    conn.close()


def set_employee_image(emp_id, img_path):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE employees SET img_path=?, img_updated=datetime('now')
        WHERE id=?
    """, (img_path, emp_id))
    conn.commit()
    conn.close()


def set_employee_deployed(emp_id, deployed: bool):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE employees SET sig_deployed=? WHERE id=?", (1 if deployed else 0, emp_id))
    conn.commit()
    conn.close()


# ─── Layouts ──────────────────────────────────────────────────────────────────

def save_layout(name, base_image, fields: list):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO layouts (name, base_image, fields_json)
        VALUES (?, ?, ?)
    """, (name, base_image, json.dumps(fields)))
    layout_id = cur.lastrowid
    conn.commit()
    conn.close()
    return layout_id


def get_layout(layout_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM layouts WHERE id=?", (layout_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["fields"] = json.loads(d["fields_json"])
        return d
    return None


def get_active_layout():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM layouts WHERE is_active=1 ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["fields"] = json.loads(d["fields_json"])
        return d
    return None


def set_active_layout(layout_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE layouts SET is_active=0")
    cur.execute("UPDATE layouts SET is_active=1 WHERE id=?", (layout_id,))
    conn.commit()
    conn.close()


def get_all_layouts():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM layouts ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def update_layout_fields(layout_id, fields: list):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE layouts SET fields_json=? WHERE id=?", (json.dumps(fields), layout_id))
    conn.commit()
    conn.close()


# ─── Deploy Log ───────────────────────────────────────────────────────────────

def log_deploy(employee_id, email, status, message=""):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO deploy_log (employee_id, email, status, message)
        VALUES (?, ?, ?, ?)
    """, (employee_id, email, status, message))
    conn.commit()
    conn.close()


def get_deploy_log(limit=100):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM deploy_log ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ─── Settings ─────────────────────────────────────────────────────────────────

def get_setting(key, default=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


# ─── Stats ────────────────────────────────────────────────────────────────────

def get_stats():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as total FROM employees WHERE active=1")
    total = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as c FROM employees WHERE active=1 AND img_path IS NOT NULL")
    generated = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM employees WHERE active=1 AND sig_deployed=1")
    deployed = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM layouts")
    layouts = cur.fetchone()["c"]
    conn.close()
    return {"total": total, "generated": generated, "deployed": deployed, "layouts": layouts}
