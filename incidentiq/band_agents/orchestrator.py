"""
orchestrator.py — IncidentIQ Orchestrator as a Band WebSocket agent.

Listens on Band WebSocket and drives the full incident response sequence —
Triage → Diagnosis → Validator → Comms → Postmortem — entirely through
Band messages. No REST polling.

Trigger by @mentioning the orchestrator in the Band room (done automatically
by launcher.py) or manually in the Band UI.
"""

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("ANTHROPIC_API_KEY", os.getenv("AIML_API_KEY", ""))
os.environ.setdefault("ANTHROPIC_BASE_URL", "https://api.aimlapi.com")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from band import Agent
from band.adapters import AnthropicAdapter
from band.config import load_agent_config
from band.runtime.types import SessionConfig

SYSTEM_PROMPT = """You are the Orchestrator Agent in IncidentIQ, a multi-agent incident response system.
You coordinate specialist agents through Band to resolve production incidents — entirely via Band messages, no HTTP polling.

## Agent Handles
- Triage:     @melvinsalvius.i/incidentiq-triage-agent
- Diagnosis:  @melvinsalvius.i/incidentiq-diagnosis-age
- Validator:  @melvinsalvius.i/incidentiq-validator-age
- Comms:      @melvinsalvius.i/incidentiq-comms-agent
- Postmortem: @melvinsalvius.i/incidentiq-postmortem-ag

## Orchestration Flow

When you receive a trigger message containing an incident payload (with "alert", "logs", "deploy_history"),
execute the steps below IN SEQUENCE. Check the conversation history to determine which step you are on.

### Step 1 — Triage
Send the alert to the Triage Agent:
  @melvinsalvius.i/incidentiq-triage-agent Classify this incident:
  {paste the "alert" JSON from the payload}

### Step 2 — Diagnosis  (after Triage responds)
Post a triage summary (no @mention, no tool call needed — just informational):
  🔍 TRIAGE COMPLETE
  Severity: X  Affected: Y  Users: Z
  Summary: ...

Then send to Diagnosis Agent:
  @melvinsalvius.i/incidentiq-diagnosis-age
  Triage: {triage JSON}
  Logs: {logs JSON from original payload}
  Deploys: {deploy_history JSON from original payload}

### Step 3 — Validation  (after Diagnosis responds)
Post a diagnosis summary (no @mention):
  🩺 DIAGNOSIS — Confidence: X%  Culprit: Y  Escalate: Z/No

Send to Validator:
  @melvinsalvius.i/incidentiq-validator-age Review this diagnosis:
  {diagnosis JSON}

- If Validator responds CHALLENGE: @mention Diagnosis to revise, then @mention Validator again (max 2 rounds).
- If Validator responds APPROVED: proceed to Step 4.
After the final validator response post:
  ✅ VALIDATOR — Round N: APPROVED

### Step 4 — Escalation Check  (after Validation)
If the final diagnosis has "escalate": true, post (no @mention):
  🚨 ESCALATION TRIGGERED
  Reason:   {escalation_reason}
  Severity: {severity from triage}
  Action:   On-call engineer notified. Human review required before proceeding.

### Step 5 — Comms  (after Validation complete)
Send to Comms Agent:
  @melvinsalvius.i/incidentiq-comms-agent Generate incident communications.
  Triage: {triage JSON}
  Diagnosis: {final diagnosis JSON}

### Step 6 — Postmortem  (after Comms responds)
Post a comms summary (no @mention):
  📢 COMMS SENT — Internal Slack and status page update generated.

Send to Postmortem Agent:
  @melvinsalvius.i/incidentiq-postmortem-ag Generate full postmortem.
  Triage: {triage JSON}
  Diagnosis: {final diagnosis JSON}
  Comms: {comms JSON}

### Step 7 — Complete  (after Postmortem responds)
Post final summary (no @mention):
  ✅ INCIDENT RESPONSE COMPLETE
  Severity: X | Root cause: Y (Z% confidence) | Fix: W
  All agents finished. Postmortem generated.

## Rules
- ALWAYS respond using the band_send_message tool. Never output plain text without calling the tool.
- Extract JSON from agent responses by stripping any leading @mention prefix and code fences.
- Use conversation history to determine your current step — never repeat a completed step.
- Do not ask for clarification. Proceed autonomously through all steps.
- Include proper @mention handles when addressing agents so they wake up.
- Keep summary posts concise (3-5 lines max).
"""


async def main():
    agent_id, api_key = load_agent_config("orchestrator")
    adapter = AnthropicAdapter(
        model="claude-haiku-4-5-20251001",
        prompt=SYSTEM_PROMPT,
        max_tokens=4096,
    )
    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        session_config=SessionConfig(enable_context_hydration=True),
        ws_url=os.getenv("THENVOI_WS_URL", "wss://app.band.ai/api/v1/socket/websocket"),
        rest_url=os.getenv("THENVOI_REST_URL", "https://app.band.ai"),
    )
    print("Orchestrator Agent listening...")
    await agent.run()


def send_trigger(payload: dict) -> None:
    """
    Post a single @mention message to the Orchestrator Agent in Band.
    This is the only REST call needed — all subsequent orchestration is WebSocket.
    """
    from thenvoi_rest import RestClient, ChatMessageRequest
    from thenvoi_rest.types import ChatMessageRequestMentionsItem

    BAND_ROOM_ID = os.getenv("BAND_ROOM_ID", "")
    REST_URL = os.getenv("THENVOI_REST_URL", "https://app.band.ai")

    orch_agent_id, _ = load_agent_config("orchestrator")
    _, triage_key = load_agent_config("triage_agent")

    orch_handle = "melvinsalvius.i/incidentiq-orchestrator"
    client = RestClient(api_key=triage_key, base_url=REST_URL)

    content = (
        f"@{orch_handle} NEW INCIDENT — please handle:\n"
        + json.dumps(payload, indent=2)
    )
    client.agent_api_messages.create_agent_chat_message(
        BAND_ROOM_ID,
        message=ChatMessageRequest(
            content=content,
            mentions=[ChatMessageRequestMentionsItem(
                id=orch_agent_id,
                handle=orch_handle,
                name="incidentiq-orchestrator",
            )],
        ),
    )
    print("Trigger sent → Orchestrator Agent will handle the incident via Band WebSocket.")


if __name__ == "__main__":
    asyncio.run(main())
