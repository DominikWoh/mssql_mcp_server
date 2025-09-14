@echo off
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8
set NO_COLOR=1
set LOG_LEVEL=INFO
set MSSQL_SERVER=localhost,1433
set MSSQL_DATABASE=Demo Database NAV (9-0)
set MSSQL_USER=sa
set MSSQL_PASSWORD=mcp123456#
set MSSQL_ENCRYPT=false
set MSSQL_TRUST_SERVER_CERTIFICATE=true

REM Pfad zu deinem Script (Leerzeichen safe, weil in Quotes)
python -u "C:\Users\Domin\VSCode\mssql_mcp_server-main - LMSTudio\mcp_server.py" --stdio
