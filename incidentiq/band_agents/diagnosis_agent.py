import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("ANTHROPIC_API_KEY", os.getenv("AIML_API_KEY", ""))
os.environ.setdefault("ANTHROPIC_BASE_URL", "https://api.aimlapi.com")

from band import Agent
from band.adapters import AnthropicAdapter
from band.config import load_agent_config

SYSTEM_PROMPT = """You are the Diagnosis Agent in IncidentIQ, a multi-agent incident response system.

When given log lines, deploy history, and triage context, diagnose the root cause:
1. Cross-reference log errors against deploy history timing
2. Form a root cause hypothesis
3. Assign confidence 0-100
4. Identify culprit (type, deploy_id, detail)
5. Suggest fix direction
6. Set escalate: true if confidence < 60 or cause is external/unknown

If you receive a CHALLENGE from the Validator Agent, revise your analysis and increment "revision".

Respond by calling the send_message tool with:
- mentions: ["@melvinsalvius.i/incidentiq-orchestrator"]
- content: a JSON object ONLY, no preamble, no markdown fences:

{"root_cause_hypothesis":"...","confidence":92,"culprit":{"type":"deploy","deploy_id":"deploy-4821","detail":"..."},"fix_direction":"...","escalate":false,"escalation_reason":null,"revision":1}
"""


async def main():
    agent_id, api_key = load_agent_config("diagnosis_agent")
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
    print("Diagnosis Agent listening...")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
