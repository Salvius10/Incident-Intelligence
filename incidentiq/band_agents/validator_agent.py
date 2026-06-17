import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("ANTHROPIC_API_KEY", os.getenv("AIML_API_KEY", ""))
os.environ.setdefault("ANTHROPIC_BASE_URL", "https://api.aimlapi.com")

from band import Agent
from band.adapters import AnthropicAdapter
from band.config import load_agent_config

SYSTEM_PROMPT = """You are the Validator Agent in IncidentIQ. Your role is adversarial — you challenge the Diagnosis Agent's hypothesis to force rigorous analysis.

When you receive a diagnosis JSON:
1. Look for gaps, assumptions, or alternative explanations
2. Check if the deploy-to-incident timing correlation is strong enough
3. Challenge any low-confidence claims (< 85)
4. Suggest what additional evidence would be needed

If confidence >= 85 and reasoning is sound, approve. Otherwise challenge.

Respond by calling the send_message tool with:
- mentions: ["@melvinsalvius.i/incidentiq-orchestrator"]
- content: a JSON object ONLY, no preamble, no markdown fences:

Approved: {"verdict":"APPROVED","feedback":"Reasoning is sound. Proceed."}
Challenge: {"verdict":"CHALLENGE","feedback":"Specific challenge: ..."}
"""


async def main():
    agent_id, api_key = load_agent_config("validator_agent")
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
    print("Validator Agent listening...")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
