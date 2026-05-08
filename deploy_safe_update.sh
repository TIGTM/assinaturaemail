#!/bin/bash
# Atualizacao segura da VPS sem perder dados de layout/usuarios.
# Uso: sudo bash deploy_safe_update.sh

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Execute como root: sudo bash deploy_safe_update.sh"
  exit 1
fi

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_ROOT="${APP_DIR}/backups"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${BACKUP_ROOT}/${STAMP}"

mkdir -p "${BACKUP_DIR}"

backup_path() {
  local src="$1"
  local label="$2"
  if [ -e "$src" ]; then
    tar -czf "${BACKUP_DIR}/${label}.tar.gz" -C "$(dirname "$src")" "$(basename "$src")"
    echo "[backup] ${src}"
  else
    echo "[skip] ${src} (nao encontrado)"
  fi
}

echo "==> Criando backup..."
backup_path "${APP_DIR}/.env" "env"
backup_path "${APP_DIR}/static/uploads" "uploads"
backup_path "${APP_DIR}/static/signatures" "signatures"
backup_path "${APP_DIR}/fonts" "fonts"
backup_path "${APP_DIR}/cert" "cert"

DB_PATH_VALUE=""
if [ -f "${APP_DIR}/.env" ]; then
  DB_PATH_VALUE="$(grep -E '^DB_PATH=' "${APP_DIR}/.env" | tail -n 1 | cut -d= -f2- || true)"
  DB_PATH_VALUE="${DB_PATH_VALUE%\"}"
  DB_PATH_VALUE="${DB_PATH_VALUE#\"}"
fi

if [ -n "$DB_PATH_VALUE" ]; then
  backup_path "$DB_PATH_VALUE" "db_external"
else
  backup_path "${APP_DIR}/data.db" "db_repo"
fi

echo "==> Atualizando codigo..."
cd "${APP_DIR}"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git fetch origin "$BRANCH"
git pull --ff-only origin "$BRANCH"

echo "==> Atualizando dependencias..."
if [ ! -d "${APP_DIR}/venv" ]; then
  python3 -m venv "${APP_DIR}/venv"
fi
source "${APP_DIR}/venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r "${APP_DIR}/requirements.txt"

echo "==> Reiniciando servico..."
systemctl restart gtm-signatures
systemctl --no-pager --full status gtm-signatures

echo ""
echo "Atualizacao concluida com sucesso."
echo "Backup salvo em: ${BACKUP_DIR}"
