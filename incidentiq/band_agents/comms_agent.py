import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("ANTHROPIC_API_KEY", os.getenv("AIML_API_KEY", ""))
os.environ.setdefault("ANTHROPIC_BASE_URL", "https://api.aimlapi.com")

from band import Agent
from band.adapters import AnthropicAdapter
from band.config import load_agent_config
from band.runtime.types import SessionConfig

SYSTEM_PROMPT = """You are the Comms Agent in IncidentIQ, a multi-agent incident response system.

When given confirmed triage and diagnosis context, produce two communications:
1. Internal Slack message — technical, for engineers/CTO. Include: severity, root cause, confidence %, culprit, fix direction, user impact, revenue impact.
2. External status page update — plain language, no jargon, no internal details. Acknowledge the issue, reassure customers, state fix is in progress.

IMPORTANT: In your JSON response, use actual newline characters in the
message strings, not escaped \n sequences. The messages should be
multi-line readable text.

Respond by calling the band_send_message tool with:
- mentions: ["@melvinsalvius.i/incidentiq-orchestrator"]
- content: a JSON object ONLY, no preamble, no markdown fences:

{"internal_slack_message":"[P1] Checkout service down...\nRoot cause: ...","status_page_update":"We are experiencing issues...\nOur team is working on it."}
"""


async def main():
    agent_id, api_key = load_agent_config("comms_agent")
    adapter = AnthropicAdapter(
        model="claude-haiku-4-5-20251001",
        prompt=SYSTEM_PROMPT,
    )
    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        session_config=SessionConfig(enable_context_hydration=False),
        ws_url=os.getenv("THENVOI_WS_URL", "wss://app.band.ai/api/v1/socket/websocket"),
        rest_url=os.getenv("THENVOI_REST_URL", "https://app.band.ai"),
    )
    print("Comms Agent listening...")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
