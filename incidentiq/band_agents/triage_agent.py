import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("ANTHROPIC_API_KEY", os.getenv("AIML_API_KEY", ""))
os.environ.setdefault("ANTHROPIC_BASE_URL", "https://api.aimlapi.com")

from band import Agent
from band.adapters import AnthropicAdapter
from band.config import load_agent_config

SYSTEM_PROMPT = """You are the Triage Agent in IncidentIQ, a multi-agent incident response system.

When you receive an incident alert payload (JSON), classify it:
1. Severity: P1 (critical/total outage), P2 (major degradation), P3 (minor)
2. Affected systems (list)
3. Regions impacted (list)
4. Users impacted (integer)
5. Business impact (revenue/min string)
6. Incident start timestamp (ISO 8601)
7. One-line summary

Respond by calling the send_message tool with:
- mentions: ["@melvinsalvius.i/incidentiq-orchestrator"]
- content: a JSON object ONLY, no preamble, no markdown fences:

{"severity":"P1","affected_systems":["name"],"regions":["r1"],"users_impacted":12400,"business_impact":"$8200/min revenue impact","incident_start":"2026-06-14T03:47:00Z","summary":"One-line description."}
"""


async def main():
    agent_id, api_key = load_agent_config("triage_agent")
    adapter = AnthropicAdapter(
        model="claude-haiku-4-5-20251001",
        system_prompt=SYSTEM_PROMPT,
    )
    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        ws_url=os.getenv("THENVOI_WS_URL", "wss://app.band.ai/api/v1/socket/websocket"),
        rest_url=os.getenv("THENVOI_REST_URL", "https://app.band.ai"),
    )
    print("Triage Agent listening...")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
