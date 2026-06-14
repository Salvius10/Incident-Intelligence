"""
Comms Agent — reads Band state (Triage + Diagnosis outputs) and generates
internal stakeholder communications and external status page updates.
Reacts to every Band update (Band integration added later).
"""

import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"
MODEL = "meta-llama/Meta-Llama-3.1-8B-Instruct"

SYSTEM_PROMPT = """You are a Comms Agent for a production incident response system.
You will receive a triage summary and a diagnosis report for an active incident.
Your job is to generate two communications.

Respond ONLY with a valid JSON object — no markdown, no explanation, no preamble.

Required fields:
- internal_slack_message: string — technical message for engineering leads and CTO.
  Must include: severity level, affected systems, number of users impacted, root cause
  with confidence percentage, deploy ID if implicated, and current fix direction.
  Can be direct and use technical terminology.
- status_page_update: string — external customer-facing message. Plain language only.
  Must NOT contain: config variable names, deploy IDs, confidence percentages, internal
  system names, or any technical jargon. Should acknowledge the issue, reassure customers,
  and state that a fix is in progress.

Example output shape:
{
  "internal_slack_message": "🔴 [P1] Checkout service down — 94% error rate, 12,400 users affected (US-East, EU-West). Root cause identified (92% confidence): DB connection pool exhausted after deploy-4821 reduced DB_POOL_SIZE from 50 to 20. Fix: rolling back DB_POOL_SIZE to 50. Revenue impact: ~$8,200/min.",
  "status_page_update": "We are currently experiencing issues with our checkout system. Our team has identified the cause and a fix is being deployed. We apologize for the inconvenience and will update this page once resolved."
}"""


def _strip_fences(text: str) -> str:
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


def run_comms_agent(triage_output: dict, diagnosis_output: dict) -> dict:
    api_key = os.getenv("FEATHERLESS_API_KEY")
    if not api_key:
        raise RuntimeError("FEATHERLESS_API_KEY not set in environment")

    user_message = (
        f"Triage output:\n{json.dumps(triage_output, indent=2)}\n\n"
        f"Diagnosis output:\n{json.dumps(diagnosis_output, indent=2)}"
    )

    try:
        response = requests.post(
            f"{FEATHERLESS_BASE_URL}/chat/completions",
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
            },
            timeout=30,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        raise

    raw = _strip_fences(response.json()["choices"][0]["message"]["content"].strip())

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Failed to parse model response as JSON: {e}")
        print(f"Raw response:\n{raw}")
        raise


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

    result = run_comms_agent(triage_output, diagnosis_output)
    print(json.dumps(result, indent=2))
