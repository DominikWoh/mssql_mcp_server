# MSSQL MCP Server für LM Studio

Ein vollständig MCP-kompatibler Server für den Zugriff auf MS SQL Datenbanken aus LM Studio heraus.

## 📋 Voraussetzungen

- Python 3.10+
- MS SQL Server (lokal oder remote)
- LM Studio (v0.3.17+)

## 🚀 Schnellstart

### 1. Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

### 2. Konfiguration anpassen

Bearbeiten Sie die `.env` Datei mit Ihren MS SQL Zugangsdaten:

```env
# MSSQL-Verbindung
MSSQL_SERVER=localhost,1433
MSSQL_DATABASE=Demo Database NAV (9-0)
MSSQL_USER=sa
MSSQL_PASSWORD=mcp123456#
MSSQL_ENCRYPT=false
MSSQL_TRUST_SERVER_CERTIFICATE=true

# Sicherheit/Limitierung
ALLOW_SCHEMAS=dbo
ROW_LIMIT=500
QUERY_TIMEOUT=10
LOG_LEVEL=INFO
```

### 3. MCP Server starten

```bash
python mcp_server.py
```

### 4. LM Studio konfigurieren

Fügen Sie diese Konfiguration in LM Studio ein:

1. Öffnen Sie LM Studio
2. Gehen Sie zu "Program" → "Install" → "Edit mcp.json"
3. Fügen Sie folgende Konfiguration hinzu:

```json
{
  "mcpServers": {
    "mssql-mcp": {
      "command": "python",
      "args": ["mcp_server.py"],
      "cwd": "c:\\Users\\Domin\\VSCode\\mssql_mcp_server-main - LMSTudio",
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
}
```

### 5. Verbindung testen

Starten Sie LM Studio neu und testen Sie die Verbindung mit:
```
Was sind die verfügbaren MCP Tools?
```

## 🛠️ Verfügbare Tools

| Tool | Beschreibung | Parameter |
|------|-------------|-----------|
| `tables` | Listet alle verfügbaren Tabellen auf | - |
| `columns` | Zeigt Spalteninformationen einer Tabelle | `table` (String) |
| `query` | Führt eine SQL-Abfrage aus | `sql` (String) |
| `sample` | Holt Beispieldaten aus einer Tabelle | `table` (String), `n` (Integer, optional) |
| `stats` | Zeigt Tabellenstatistiken an | `table` (String), `sample_n` (Integer, optional) |
| `explain` | Erklärt eine SQL-Abfrage | `sql` (String) |

## 📝 Beispiele

### Tabellen auflisten
```
Zeige mir alle verfügbaren Tabellen
```

### Spalten anzeigen
```
Zeige mir die Spalten der Tabelle CRONUS AG$Customer
```

### Daten abfragen
```
Führe folgende SQL-Abfrage aus: SELECT TOP 10 * FROM CRONUS AG$Customer
```

### Beispieldaten holen
```
Hole 5 Beispieldaten aus der Tabelle CRONUS AG$Sales Header
```

## 🔧 Fehlerbehebung

### Verbindung fehlschlägt
1. Prüfen Sie, ob MS SQL Server läuft
2. Überprüfen Sie die Zugangsdaten in `.env`
3. Stellen Sie sicher, dass der Port 1433 erreichbar ist

### Tools werden nicht angezeigt
1. Starten Sie LM Studio neu
2. Prüfen Sie die mcp.json Konfiguration
3. Starten Sie den MCP Server neu

### JSON Fehler
1. Stellen Sie sicher, dass alle Abrechnungen korrekt sind
2. Überprüfen Sie die SQL-Syntax
3. Prüfen Sie die Tabellen- und Spaltennamen

## 📁 Projektstruktur

```
mssql_mcp_server-main/
├── .env                    # Konfigurationsdatei
├── requirements.txt        # Python-Abhängigkeiten
├── mcp_server.py          # Haupt-Serverdatei
├── README_LM_STUDIO.md    # Diese Anleitung
├── mssql_mcp_server/      # Server-Code
│   ├── __init__.py
│   ├── __main__.py
│   ├── server.py          # Kernlogik
│   └── http.py            # HTTP-Server (nicht verwendet)
└── .env.example           # Beispielkonfiguration
```

## 🔄 Updates

Der Server wird automatisch aktualisiert, wenn neue Tools oder Funktionen hinzugefügt werden.

## 📞 Support

Bei Problemen überprüfen Sie:
1. Die Logs im Terminal
2. Die LM Studio Konsole
3. Die MS SQL Server Verbindung