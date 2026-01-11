# Multi-Agent Orchestrator (LangGraph + FastMCP)

Production-ready scaffold for an India-focused AI assistant with three agents:
- **Weather agent** → Open-Meteo via weather tool
- **News agent** → RSS (Google News India) via news tool
- **Stock agent** → YFinance via stock tool

Architecture
------------
- `app/config` – YAML config + settings loader (.env for secrets)
- `app/tools` – FastMCP tools (weather, news, stock)
- `app/agents` – LangGraph orchestration + intent routing
- `app/server` – FastAPI HTTP server (`/query`) and FastMCP server entrypoints
- `app/client` – simple HTTP client helper

Setup
-----
1) Install deps
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2) Configure secrets and models  
Create `.env` with your OpenAI key:
```
OPENAI_API_KEY=your-key
```
Adjust models / defaults in `app/config/config.yaml` if needed.

Run servers
-----------
FastAPI HTTP (orchestrator):
```bash
uvicorn app.server.main:app --host 0.0.0.0 --port 8000 --reload
```

FastMCP server (tools exposed over MCP):
```bash
python -m app.server.mcp_server  # stdio
# or HTTP:
python - <<\"PY\"
from app.server.mcp_server import run_http
run_http(host=\"0.0.0.0\", port=8001)
PY
```

Usage examples
--------------
HTTP query:
```bash
curl -X POST http://localhost:8000/query -H \"Content-Type: application/json\" -d \"{\\\"query\\\":\\\"I need Bengaluru weather today\\\"}\"
curl -X POST http://localhost:8000/query -H \"Content-Type: application/json\" -d \"{\\\"query\\\":\\\"I want today's news\\\"}\"
curl -X POST http://localhost:8000/query -H \"Content-Type: application/json\" -d \"{\\\"query\\\":\\\"I need HCL stock price today\\\"}\"
```

Response shape:
```json
{
  \"intent\": \"weather|news|stock|unknown\",
  \"tool_used\": \"weather|news|stock|general\",
  \"tool_result\": \"<tool output>\",
  \"answer\": \"LLM-formatted reply\",
  \"messages\": [{\"role\":\"user|assistant|tool\", \"content\":\"...\"}]
}
```

Logging
-------
- Configured via `app/config/config.yaml` (`logs/app.log` by default).
- Adjust log level / file path there.

Notes
-----
- Tools are MCP-compliant via `fastmcp.tools.tool`.
- LangGraph routes dynamically by intent keywords (weather/news/stock) with fallback LLM.
- News feed / stock suffix defaults are config-driven.