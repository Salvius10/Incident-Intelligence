"""
Triage Agent — reads the raw alert payload and classifies incident severity,
affected systems, user impact, and business impact. Posts structured incident
state to Band (Band integration added later).
"""

import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"
MODEL = "meta-llama/Meta-Llama-3.1-8B-Instruct"

SYSTEM_PROMPT = """You are a Triage Agent for a production incident response system.
You will receive an alert payload and must classify the incident.

Respond ONLY with a valid JSON object — no markdown, no explanation, no preamble.

Classify:
- severity: "P1" (critical/total outage), "P2" (major degradation), or "P3" (minor issue)
- affected_systems: list of impacted services
- regions: list of affected regions
- users_impacted: integer number of affected users
- business_impact: string in format "estimated $X/min revenue impact"
- incident_start: ISO timestamp from the alert
- summary: one-line human-readable description of the incident

Example output shape:
{
  "severity": "P1",
  "affected_systems": ["checkout-service"],
  "regions": ["us-east", "eu-west"],
  "users_impacted": 12400,
  "business_impact": "estimated $8200/min revenue impact",
  "incident_start": "2026-06-14T03:47:00Z",
  "summary": "Checkout service experiencing 94% error rate affecting 12,400 users across US-East and EU-West."
}"""


def load_alert(path="mock_data/incident_payload.json"):
    with open(path) as f:
        payload = json.load(f)
    return payload["alert"]


def run_triage_agent(alert: dict) -> dict:
    api_key = os.getenv("FEATHERLESS_API_KEY")
    if not api_key:
        raise RuntimeError("FEATHERLESS_API_KEY not set in environment")

    user_message = f"Classify this production alert:\n\n{json.dumps(alert, indent=2)}"

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
                "temperature": 0.1,
            },
            timeout=30,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        raise

    raw = response.json()["choices"][0]["message"]["content"].strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Failed to parse model response as JSON: {e}")
        print(f"Raw response:\n{raw}")
        raise


if __name__ == "__main__":
    alert = load_alert()
    result = run_triage_agent(alert)
    print(json.dumps(result, indent=2))
