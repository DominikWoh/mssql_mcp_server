# MCP Server an Open WebUI binden

Es gibt mehrere Möglichkeiten, den MCP Server mit Open WebUI zu verbinden:

## 🚀 Methode 1: Direkte HTTP Integration (Empfohlen)

Open WebUI kann direkt mit HTTP-basierten MCP Servern kommunizieren.

### 1.1 Server starten

Starten Sie den MCP Server als HTTP-Server:

```bash
python mcp_server.py
```

Der Server läuft auf `http://localhost:8000`

### 1.2 Open WebUI Konfiguration

Fügen Sie diese Konfiguration zu Ihrer Open WebUI-Konfiguration hinzu:

**Option A: Via Umgebungsvariablen**
```bash
export OPENWEBUI_MCP_SERVERS='{
  "mssql-server": {
    "command": "python",
    "args": ["mcp_server.py"],
    "cwd": "/pfad/zu/mssql_mcp_server-main",
    "env": {
      "MSSQL_SERVER": "localhost,1433",
      "MSSQL_DATABASE": "Demo Database NAV (9-0)",
      "MSSQL_USER": "sa",
      "MSSQL_PASSWORD": "mcp123456#",
      "MSSQL_ENCRYPT": "false",
      "MSSQL_TRUST_SERVER_CERTIFICATE": "true",
      "LOG_LEVEL": "INFO"
    }
  }
}'
```

**Option B: Via Konfigurationsdatei**
Erstellen Sie eine Datei `mcp_config.json`:
```json
{
  "mssql-server": {
    "command": "python",
    "args": ["mcp_server.py"],
    "cwd": "/pfad/zu/mssql_mcp_server-main",
    "env": {
      "MSSQL_SERVER": "localhost,1433",
      "MSSQL_DATABASE": "Demo Database NAV (9-0)",
      "MSSQL_USER": "sa",
      "MSSQL_PASSWORD": "mcp123456#",
      "MSSQL_ENCRYPT": "false",
      "MSSQL_TRUST_SERVER_CERTIFICATE": "true",
      "LOG_LEVEL": "INFO"
    }
  }
}
```

Und setzen Sie:
```bash
export OPENWEBUI_MCP_CONFIG_PATH="/pfad/zu/mcp_config.json"
```

## 🔌 Methode 2: Via MCP Proxy

Verwenden Sie einen MCP Proxy wie `mcp-proxy` oder `npx @modelcontextprotocol/server-proxy`.

### 2.1 MCP Proxy installieren
```bash
npm install -g @modelcontextprotocol/server-proxy
```

### 2.2 Proxy konfigurieren
```bash
mcp-proxy --server mssql-server --command python --args mcp_server.py --cwd /pfad/zu/mssql_mcp_server-main
```

### 2.3 Open WebUI verbinden
```bash
export OPENWEBUI_MCP_SERVERS='{
  "mssql-server": {
    "command": "mcp-proxy",
    "args": ["--server", "mssql-server", "--command", "python", "--args", "mcp_server.py"]
  }
}'
```

## 🌐 Methode 3: Via Docker Compose

Wenn Sie Docker verwenden, können Sie alles in einem Compose-File zusammenfassen:

```yaml
version: '3.8'
services:
  mssql-mcp-server:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MSSQL_SERVER=localhost,1433
      - MSSQL_DATABASE=Demo Database NAV (9-0)
      - MSSQL_USER=sa
      - MSSQL_PASSWORD=mcp123456#
      - MSSQL_ENCRYPT=false
      - MSSQL_TRUST_SERVER_CERTIFICATE=true
      - LOG_LEVEL=INFO
    volumes:
      - ./mcp_server.py:/app/mcp_server.py
      - ./.env:/app/.env

  openwebui:
    image: ghcr.io/open-webui/open-webui:main
    ports:
      - "3000:8080"
    environment:
      - OPENWEBUI_MCP_SERVERS='{"mssql-server": {"host": "mssql-mcp-server", "port": 8000}}'
    depends_on:
      - mssql-mcp-server
```

## 📋 Methode 4: Via Open WebUI UI-Einstellungen

1. Öffnen Sie Open WebUI
2. Gehen Sie zu "Settings" → "MCP Servers"
3. Klicken Sie auf "Add Server"
4. Füllen Sie die Felder aus:
   - **Name**: `mssql-server`
   - **Command**: `python`
   - **Args**: `mcp_server.py`
   - **Working Directory**: `/pfad/zu/mssql_mcp_server-main`
   - **Environment Variables**: 
     ```
     MSSQL_SERVER=localhost,1433
     MSSQL_DATABASE=Demo Database NAV (9-0)
     MSSQL_USER=sa
     MSSQL_PASSWORD=mcp123456#
     MSSQL_ENCRYPT=false
     MSSQL_TRUST_SERVER_CERTIFICATE=true
     LOG_LEVEL=INFO
     ```

## 🔧 Methode 5: Via Open WebUI Docker Environment

Wenn Sie Open WebUI als Docker-Container betreiben:

```bash
docker run -d \
  --name openwebui \
  -p 3000:8080 \
  -e OPENWEBUI_MCP_SERVERS='{
    "mssql-server": {
      "command": "python",
      "args": ["mcp_server.py"],
      "cwd": "/pfad/zu/mssql_mcp_server-main",
      "env": {
        "MSSQL_SERVER": "localhost,1433",
        "MSSQL_DATABASE": "Demo Database NAV (9-0)",
        "MSSQL_USER": "sa",
        "MSSQL_PASSWORD": "mcp123456#",
        "MSSQL_ENCRYPT": "false",
        "MSSQL_TRUST_SERVER_CERTIFICATE": "true",
        "LOG_LEVEL": "INFO"
      }
    }
  }' \
  ghcr.io/open-webui/open-webui:main
```

## 🧪 Testen der Verbindung

Nach der Konfiguration können Sie die Verbindung testen:

1. Starten Sie Open WebUI neu
2. Erstellen Sie eine neue Chat-Sitzung
3. Fragen Sie: "Was sind die verfügbaren MCP Tools?"
4. Die Antwort sollte die MSSQL Tools anzeigen

## 🐛 Fehlerbehebung

### Verbindung scheitert
- Prüfen Sie, ob der MCP Server läuft
- Überprüfen Sie die Pfade in der Konfiguration
- Testen Sie die Verbindung mit curl:
  ```bash
  curl -X POST http://localhost:8000/mcp -H "Content-Type: application/json" -d '{"action": "ping"}'
  ```

### Tools werden nicht angezeigt
- Starten Sie Open WebUI neu
- Prüfen Sie die Logs auf Fehler
- Stellen Sie sicher, dass die Umgebungsvariablen korrekt gesetzt sind

### Performance-Probleme
- Reduzieren Sie die `ROW_LIMIT` in der .env Datei
- Erhöhen Sie den `QUERY_TIMEOUT` bei komplexen Abfragen
- Prüfen Sie die MS SQL Server Performance

## 📝 Beispiel-Abfragen in Open WebUI

Nach der erfolgreichen Verbindung können Sie:

```
Zeige mir alle verfügbaren Tabellen
```

```
Zeige mir die Spalten der Tabelle CRONUS AG$Customer
```

```
Führe folgende SQL-Abfrage aus: SELECT TOP 10 * FROM CRONUS AG$Customer
```

```
Hole 5 Beispieldaten aus der Tabelle CRONUS AG$Sales Header
```

```
Erkläre mir diese SQL-Abfrage: SELECT * FROM CRONUS AG$Customer WHERE Customer No_ = 'CUST001'