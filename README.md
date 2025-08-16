# MSSQL MCP Server (minimal)

Read-only MCP-kompatibler STDIO-Server für MS SQL mit Tools:
- `tables` – listet Tabellen (oder Whitelist)
- `columns` – Spalten-Metadaten
- `query` – SELECT (mit TOP-Limit + Timeout)
- `sample` – `SELECT TOP n * FROM table`

## Quickstart

```bash
git clone https://github.com/DominikWoh/mssql_mcp_server && cd mssql-mcp
./scripts/install.sh
cp .env.example .env && nano .env
source .venv/bin/activate
