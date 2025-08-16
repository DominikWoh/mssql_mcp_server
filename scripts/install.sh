#!/usr/bin/env bash
set -euo pipefail

# Minimal-Installer (Ubuntu/Debian)
# - erstellt venv
# - installiert Abhängigkeiten
# - schreibt .env aus Beispiel, falls nicht vorhanden

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python3 fehlt." >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .

[ -f .env ] || cp .env.example .env

echo "Installation fertig. Aktiviere mit:  source .venv/bin/activate"
echo "Test:"
echo 'printf "%s\n" "{\"action\":\"ping\"}" | mssql-mcp'
