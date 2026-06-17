import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("ANTHROPIC_API_KEY", os.getenv("AIML_API_KEY", ""))
os.environ.setdefault("ANTHROPIC_BASE_URL", "https://api.aimlapi.com")

from band import Agent
from band.adapters import AnthropicAdapter
from band.config import load_agent_config

SYSTEM_PROMPT = """You are the Postmortem Agent in IncidentIQ.

When given the full incident context (triage, diagnosis, validation rounds, comms), produce a complete RCA document in markdown:

1. # Incident Postmortem — {severity} — {timestamp}
2. ## Summary (2-3 sentences)
3. ## Timeline (chronological bullets)
4. ## Root Cause (expanded explanation)
5. ## Impact (duration, users, revenue, SLA breach)
6. ## Resolution (fix applied)
7. ## Contributing Factors (2-3 factors)
8. ## Action Items (3 items in - [ ] format with owning team)

Respond by calling the send_message tool with:
- mentions: ["@melvinsalvius.i/incidentiq-orchestrator"]
- content: the full markdown document (no JSON wrapper, just raw markdown)
"""


async def main():
    agent_id, api_key = load_agent_config("postmortem_agent")
    adapter = AnthropicAdapter(
        model="claude-haiku-4-5-20251001",
        system_prompt=SYSTEM_PROMPT,
        max_tokens=2048,
    )
    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        ws_url=os.getenv("THENVOI_WS_URL", "wss://app.band.ai/api/v1/socket/websocket"),
        rest_url=os.getenv("THENVOI_REST_URL", "https://app.band.ai"),
    )
    print("Postmortem Agent listening...")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
