"""
Diagnosis Agent — reads logs and deploy history (plus Triage Agent's incident
state) to hypothesize root cause, assign confidence, identify the culprit, and
recommend a fix direction. Posts findings to Band (Band integration added later).
"""

import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

AIML_BASE_URL = "https://api.aimlapi.com/v1"
MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are a Diagnosis Agent for a production incident response system.
You will receive system logs, recent deploy history, and a triage summary. Your job is to
perform root cause analysis.

Cross-reference the log errors against the deploy history timestamps. Identify which deploy
(if any) correlates with the incident timing. Form a root cause hypothesis.

Respond ONLY with a valid JSON object — no markdown, no explanation, no preamble.

Required fields:
- root_cause_hypothesis: string — detailed explanation of the likely root cause
- confidence: integer 0-100 — your confidence in the hypothesis
- culprit: object with fields:
    - type: "configuration" | "code" | "dependency" | "infrastructure" | "unknown"
    - deploy_id: the deploy ID if a deploy is implicated, otherwise null
    - detail: specific detail about the culprit
- fix_direction: string — recommended remediation action
- escalate: boolean — true if confidence < 60 or root cause cannot be determined
- escalation_reason: string if escalate is true, otherwise null

Example output shape:
{
  "root_cause_hypothesis": "Database connection pool exhausted following config deploy at 03:31. DB_POOL_SIZE reduced from 50 to 20, causing request queue buildup and deadlock cascade under load.",
  "confidence": 78,
  "culprit": {
    "type": "configuration",
    "deploy_id": "deploy-4821",
    "detail": "DB_POOL_SIZE changed from 50 to 20"
  },
  "fix_direction": "Roll back DB_POOL_SIZE to 50 for checkout-service.",
  "escalate": false,
  "escalation_reason": null
}"""


def load_logs_and_deploys(path="mock_data/incident_payload.json"):
    with open(path) as f:
        payload = json.load(f)
    return payload["logs"], payload["deploy_history"]


def run_diagnosis_agent(logs: list, deploy_history: list, triage_context: dict) -> dict:
    api_key = os.getenv("AIML_API_KEY")
    if not api_key:
        raise RuntimeError("AIML_API_KEY not set in environment")

    user_message = (
        f"Triage context:\n{json.dumps(triage_context, indent=2)}\n\n"
        f"System logs:\n{json.dumps(logs, indent=2)}\n\n"
        f"Deploy history:\n{json.dumps(deploy_history, indent=2)}"
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
                "temperature": 0.1,
            },
            timeout=60,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        raise

    raw = response.json()["choices"][0]["message"]["content"].strip()
    # strip markdown code fences if the model wrapped the JSON
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Failed to parse model response as JSON: {e}")
        print(f"Raw response:\n{raw}")
        raise


if __name__ == "__main__":
    logs, deploy_history = load_logs_and_deploys()

    triage_context = {
        "severity": "P1",
        "affected_systems": ["checkout-service"],
        "regions": ["us-east", "eu-west"],
        "users_impacted": 12400,
        "business_impact": "$8200/min revenue impact",
        "incident_start": "2026-06-14T03:47:00Z",
        "summary": "Checkout service experiencing 94% error rate affecting 12,400 users across US-East and EU-West."
    }

    result = run_diagnosis_agent(logs, deploy_history, triage_context)
    print(json.dumps(result, indent=2))
