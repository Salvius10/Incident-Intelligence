# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Run Commands

All commands run from `incidentiq/` using the venv Python:

```bash
# Direct API pipeline (no Band agents required)
python main.py
python run_scenario.py mock_data/incident_payload_memory_leak.json
python run_scenario.py mock_data/incident_payload_third_party.json

# Full Band multi-agent flow
python launcher.py        # scenario 1 — checkout outage (default)
python launcher.py 2      # scenario 2 — memory leak
python launcher.py 3      # scenario 3 — third-party outage

# FastAPI server (Band agents must already be running via launcher.py)
uvicorn app:app --reload
```

Install dependencies (venv already exists at `incidentiq/venv/`):
```bash
pip install -r requirements.txt
```

The Band SDK packages (`thenvoi_rest`, `band`) are not in `requirements.txt` — they are installed separately into the venv.

## Architecture: Two Execution Paths

The project has **two parallel ways to run the same 4-agent pipeline**:

### Path 1 — Direct API Pipeline (`main.py` / `run_scenario.py`)
```
main.py / run_scenario.py
  └── pipeline.py (run_pipeline)
        ├── agents/triage_agent.py      → Featherless API (Llama 3.1 8B)
        ├── agents/diagnosis_agent.py   → AIML API (Claude Haiku)
        ├── agents/comms_agent.py       → Featherless API (Llama 3.1 8B)
        ├── agents/postmortem_agent.py  → AIML API (Claude Haiku)
        └── coordination/band_client.py (fire-and-forget Band mirror)
```
Each agent in `agents/` makes a direct `requests.post` to its LLM API and returns a parsed dict. `pipeline.py` chains them sequentially. `band_client.py` mirrors outputs to the Band room but failures are swallowed — the pipeline never blocks on Band.

### Path 2 — Band WebSocket Multi-Agent (`launcher.py`)
```
launcher.py
  ├── starts 6 subprocesses (band_agents/*.py) — all WebSocket listeners
  └── send_trigger() → one REST @mention to Orchestrator
        └── band_agents/orchestrator.py (LLM drives sequence via @mentions)
              ├── band_agents/triage_agent.py
              ├── band_agents/diagnosis_agent.py
              ├── band_agents/validator_agent.py   ← only exists in this path
              ├── band_agents/comms_agent.py
              └── band_agents/postmortem_agent.py
```
Each agent in `band_agents/` is a long-lived `band.Agent` WebSocket listener using `AnthropicAdapter` (Claude Haiku via AIML API). The orchestrator is also a WebSocket agent — it uses conversation history (`enable_context_hydration=True`) to track which step it's on and drives the sequence by @mentioning agents. The only HTTP call is the initial `send_trigger()`.

**Key difference**: Band Path adds a **Validator Agent** (adversarial challenge/approve loop on the diagnosis, up to 2 rounds) that does not exist in the Direct API path.

## Agent Config

Band agent IDs and API keys come from two sources (checked in order):
1. Environment variables in `.env` (`BAND_TRIAGE_AGENT_ID`, `BAND_TRIAGE_API_KEY`, etc.)
2. `incidentiq/agent_config.yaml` — loaded by `band.config.load_agent_config(key)`

The `.env` file must define: `AIML_API_KEY`, `FEATHERLESS_API_KEY`, `BAND_ROOM_ID`, `THENVOI_WS_URL`, `THENVOI_REST_URL`, and per-agent `BAND_*_AGENT_ID` / `BAND_*_API_KEY` pairs for all 6 agents (triage, diagnosis, validator, comms, postmortem, orchestrator).

## Payload Structure

All three mock payloads follow this shape:
```json
{
  "alert": { "service", "error_rate", "active_users", "timestamp", "region", "revenue_per_minute" },
  "logs": ["string", ...],
  "deploy_history": [{ "id", "time", "author", "change", "service" }, ...]
}
```
`pipeline.py` expects exactly these top-level keys (`payload["alert"]`, `payload["logs"]`, `payload["deploy_history"]`).

## LLM Provider Split

| Agent | Provider | Model |
|-------|----------|-------|
| Triage, Comms (`agents/`) | Featherless (`api.featherless.ai/v1`) | `meta-llama/Meta-Llama-3.1-8B-Instruct` |
| Diagnosis, Postmortem (`agents/`) | AIML API (`api.aimlapi.com/v1`) | `claude-haiku-4-5-20251001` |
| All `band_agents/` | AIML API (via `ANTHROPIC_BASE_URL` override) | `claude-haiku-4-5-20251001` |

The `band_agents/` agents set `os.environ["ANTHROPIC_BASE_URL"] = "https://api.aimlapi.com"` before importing the Band SDK so the `AnthropicAdapter` routes to AIML instead of Anthropic directly.

## Coordination Layer (`coordination/band_client.py`)

Used only by Path 1. Maintains a local `band_history.json` as the authoritative inter-agent store — `pipeline.py` reads this to pass context between agents. Band room posting is fire-and-forget (all exceptions swallowed). `reset_band_history()` clears the file at pipeline start.

## Band Room Setup

Run once to create the Band room and add all agents as participants:
```bash
python setup_band.py
```
Copy the printed `BAND_ROOM_ID` into `.env`.
