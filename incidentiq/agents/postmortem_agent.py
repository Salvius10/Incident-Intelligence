"""
Postmortem Agent — reads the full incident history (Triage, Diagnosis, and
Comms agent outputs) and generates a complete RCA report in markdown,
saved to postmortem_output.md. Reads full Band history (Band integration
added later).
"""

import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

AIML_BASE_URL = "https://api.aimlapi.com/v1"
MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are a Postmortem Agent for a production incident response system.
You will receive outputs from the Triage Agent, Diagnosis Agent, and Comms Agent for a
resolved production incident. Your job is to produce a complete, professional RCA (Root
Cause Analysis) postmortem report in markdown format.

Generate the report with exactly these 8 sections in this order:

1. # Incident Postmortem — P1 — <incident_start timestamp from triage>
2. ## Summary — 2-3 sentences: what broke, estimated duration, users affected, revenue impact
3. ## Timeline — bulleted chronological list. Use these reference points:
   - Deploy time: 03:31Z (from the culprit deploy context)
   - Incident start: from triage incident_start
   - Diagnosis completed: ~30-60 seconds after incident start
   - Comms sent: immediately after diagnosis
   - Fix applied and resolved: ~5-8 minutes after incident start (pick a plausible specific time)
4. ## Root Cause — expand on the hypothesis and culprit detail; do not just repeat verbatim
5. ## Impact — duration, users affected, revenue impact; note SLA breach if incident lasted > 5 minutes (SLA threshold is 5 minutes)
6. ## Resolution — based on the fix direction from diagnosis
7. ## Contributing Factors — 2-3 plausible factors (e.g. config change not load-tested, deploy without on-call notification, no canary rollout)
8. ## Action Items — exactly 3 items in this format: `- [ ] Action description — Owning Team`

Output the markdown report directly — no JSON wrapper, no preamble, no explanation.
Start immediately with the # title line."""


def _strip_outer_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines[-1].strip() == "```":
            inner = lines[1:-1]
            return "\n".join(inner).strip()
    return stripped


def run_postmortem_agent(triage_output: dict, diagnosis_output: dict, comms_output: dict) -> str:
    api_key = os.getenv("AIML_API_KEY")
    if not api_key:
        raise RuntimeError("AIML_API_KEY not set in environment")

    user_message = (
        f"Triage Agent output:\n{json.dumps(triage_output, indent=2)}\n\n"
        f"Diagnosis Agent output:\n{json.dumps(diagnosis_output, indent=2)}\n\n"
        f"Comms Agent output:\n{json.dumps(comms_output, indent=2)}"
    )

    try:
        response = requests.post(
            f"{AIML_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.3,
                "max_tokens": 2048,
            },
            timeout=60,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        raise

    raw = response.json()["choices"][0]["message"]["content"]
    return _strip_outer_fence(raw)


if __name__ == "__main__":
    triage_output = {
        "severity": "P1",
        "affected_systems": ["checkout-service"],
        "regions": ["us-east", "eu-west"],
        "users_impacted": 12400,
        "business_impact": "$8200/min revenue impact",
        "incident_start": "2026-06-14T03:47:00Z",
        "summary": "Checkout service experiencing 94% error rate affecting 12,400 users across US-East and EU-West."
    }

    diagnosis_output = {
        "root_cause_hypothesis": "Database connection pool exhaustion following deploy-4821 at 03:31Z. The DB_POOL_SIZE was reduced from 50 to 20 connections, causing the pool to be overwhelmed during normal checkout traffic. With only 20 available connections and 847 requests queued, transactions began timing out and deadlocking. The cascade of connection timeouts and rollbacks created a feedback loop that drove the error rate to 94% by 03:47Z.",
        "confidence": 92,
        "culprit": {
            "type": "configuration",
            "deploy_id": "deploy-4821",
            "detail": "DB_POOL_SIZE reduced from 50 to 20 in checkout-service, insufficient for production load"
        },
        "fix_direction": "Immediately roll back deploy-4821 to restore DB_POOL_SIZE to 50. Monitor connection pool metrics and request queue depth during rollout. If rollback does not resolve within 5 minutes, escalate to database team for connection leak investigation.",
        "escalate": False,
        "escalation_reason": None
    }

    comms_output = {
        "internal_slack_message": "🔴 [P1] Checkout service down — 94% error rate, 12,400 users affected (US-East, EU-West). Root cause identified (92% confidence): Database connection pool exhaustion following deploy-4821 at 03:31Z. The DB_POOL_SIZE was reduced from 50 to 20 connections, causing the pool to be overwhelmed during normal checkout traffic. With only 20 available connections and 847 requests queued, transactions began timing out and deadlocking. The cascade of connection timeouts and rollbacks created a feedback loop that drove the error rate to 94% by 03:47Z. Fix: immediately roll back deploy-4821 to restore DB_POOL_SIZE to 50. Revenue impact: ~$8,200/min.",
        "status_page_update": "We are currently experiencing issues with our checkout system. Our team has identified the cause and a fix is being deployed. We apologize for the inconvenience and will update this page once resolved."
    }

    report = run_postmortem_agent(triage_output, diagnosis_output, comms_output)

    with open("postmortem_output.md", "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Postmortem saved to postmortem_output.md ({len(report)} chars)")
    print("Preview:")
    print("\n".join(report.splitlines()[:3]))
