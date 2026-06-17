"""
orchestrator.py — Drives the IncidentIQ conversation through Band.

Uses thenvoi_rest.RestClient to:
  - @mention listener agents (create_agent_chat_message)
  - Poll its own inbox for their responses (list_agent_messages)
  - Post human-readable summaries after each agent responds (create_agent_chat_event)

Does NOT run as a Band WebSocket agent — it is a sequential REST driver.
"""

import json
import os
import re
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from thenvoi_rest import RestClient, ChatMessageRequest, ChatEventRequest
from thenvoi_rest.types import ChatMessageRequestMentionsItem
from band.config import load_agent_config

load_dotenv()

BAND_ROOM_ID = os.getenv("BAND_ROOM_ID", "")
REST_URL = os.getenv("THENVOI_REST_URL", "https://app.band.ai")

AGENTS = {
    "triage":     ("melvinsalvius.i/incidentiq-triage-agent",   os.getenv("BAND_TRIAGE_AGENT_ID", "")),
    "diagnosis":  ("melvinsalvius.i/incidentiq-diagnosis-age",  os.getenv("BAND_DIAGNOSIS_AGENT_ID", "")),
    "validator":  ("melvinsalvius.i/incidentiq-validator-age",  os.getenv("BAND_VALIDATOR_AGENT_ID", "")),
    "comms":      ("melvinsalvius.i/incidentiq-comms-agent",    os.getenv("BAND_COMMS_AGENT_ID", "")),
    "postmortem": ("melvinsalvius.i/incidentiq-postmortem-ag",  os.getenv("BAND_POSTMORTEM_AGENT_ID", "")),
}


# ── Formatters ────────────────────────────────────────────────────────────────

def format_triage(result: dict) -> str:
    regions = ", ".join(result.get("regions", []))
    systems = ", ".join(result.get("affected_systems", []))
    users = result.get("users_impacted", "Unknown")
    users_str = f"{users:,}" if isinstance(users, int) else str(users)
    return (
        f"🔍 TRIAGE COMPLETE\n\n"
        f"Severity:        {result.get('severity', 'Unknown')}\n"
        f"Affected:        {systems}\n"
        f"Regions:         {regions}\n"
        f"Users impacted:  {users_str}\n"
        f"Business impact: {result.get('business_impact', 'Unknown')}\n"
        f"Summary:         {result.get('summary', '')}"
    )


def format_diagnosis(result: dict) -> str:
    revision = result.get("revision", 1)
    rev_label = (
        f"Revision {revision} (revised after Validator challenge)"
        if revision > 1 else f"Revision {revision}"
    )
    culprit = result.get("culprit", {})
    if isinstance(culprit, dict):
        culprit_str = (
            f"{culprit.get('deploy_id', 'Unknown')} — "
            f"{culprit.get('detail', 'Unknown')}"
        )
    else:
        culprit_str = str(culprit)
    escalate = "Yes" if result.get("escalate") else "No"
    return (
        f"🩺 DIAGNOSIS — {rev_label}\n\n"
        f"Root cause:   {result.get('root_cause_hypothesis', '')}\n"
        f"Confidence:   {result.get('confidence', 0)}%\n"
        f"Culprit:      {culprit_str}\n"
        f"Fix:          {result.get('fix_direction', '')}\n"
        f"Escalate:     {escalate}"
    )


def format_validator(result: dict, round_num: int) -> str:
    verdict = result.get("verdict", "UNKNOWN")
    icon = "✅" if verdict == "APPROVED" else "⚠️"
    feedback = result.get("feedback", "")
    return (
        f"{icon} VALIDATOR — Round {round_num}: {verdict}\n\n"
        f"Feedback: {feedback}"
    )


def format_escalation(diagnosis: dict) -> str:
    severity = "P1"
    return (
        f"🚨 ESCALATION TRIGGERED\n\n"
        f"Reason:   {diagnosis.get('escalation_reason', 'Confidence below threshold')}\n"
        f"Severity: {severity}\n"
        f"Action:   On-call engineer notified. Human review required before proceeding."
    )


def format_comms(result: dict) -> tuple[str, str]:
    """Returns (internal_message, external_message) as two formatted strings."""
    internal = result.get("internal_slack_message", "")
    external = result.get("status_page_update", "")
    internal = internal.replace("\\n", "\n").strip()
    external = external.replace("\\n", "\n").strip()
    return (
        f"📢 INTERNAL — Engineering & CTO\n\n{internal}",
        f"🌐 EXTERNAL — Status Page Update\n\n{external}",
    )


# ── Transport helpers ─────────────────────────────────────────────────────────

def _make_client() -> RestClient:
    _, api_key = load_agent_config("orchestrator")
    return RestClient(api_key=api_key, base_url=REST_URL)


def _mention(agent_key: str) -> ChatMessageRequestMentionsItem:
    handle, agent_id = AGENTS[agent_key]
    return ChatMessageRequestMentionsItem(
        id=agent_id,
        handle=handle,
        name=handle.split("/", 1)[-1],
    )


def _send(client: RestClient, agent_key: str, text: str) -> datetime:
    """Send @mention message to trigger an agent. Returns send time (UTC)."""
    handle, _ = AGENTS[agent_key]
    before = datetime.now(timezone.utc)
    client.agent_api_messages.create_agent_chat_message(
        BAND_ROOM_ID,
        message=ChatMessageRequest(
            content=f"@{handle} {text}",
            mentions=[_mention(agent_key)],
        ),
    )
    return before


def _post_summary(client: RestClient, text: str) -> None:
    """Post a human-readable task event to the Band room (no @mention required)."""
    try:
        client.agent_api_events.create_agent_chat_event(
            BAND_ROOM_ID,
            event=ChatEventRequest(content=text, message_type="task"),
        )
    except Exception:
        pass


def _poll(client: RestClient, sender_id: str, after: datetime, timeout: int = 120) -> str | None:
    """Poll orchestrator inbox until a message from sender_id arrives after `after`."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.agent_api_messages.list_agent_messages(BAND_ROOM_ID, status="all")
        for msg in resp.data:
            ts = msg.inserted_at
            if ts and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if msg.sender_id == sender_id and ts and ts > after:
                return msg.content
        time.sleep(3)
    return None


def _extract_json(raw: str) -> dict:
    """Strip @mention prefix and code fences, then parse JSON."""
    text = re.sub(r"^@\S+\s*", "", raw.strip())
    if text.startswith("```"):
        lines = text.split("\n", 1)
        text = lines[1] if len(lines) > 1 else text
        text = re.sub(r"```\s*$", "", text).strip()
    return json.loads(text.strip())


# ── Main orchestration ────────────────────────────────────────────────────────

def run_incident(payload: dict) -> dict:
    """
    Drive the full incident response conversation through Band.
    Returns a results dict with all agent outputs.
    """
    client = _make_client()
    results: dict = {}
    alert = payload.get("alert", {})
    logs = payload.get("logs", [])
    deploys = payload.get("deploy_history", [])

    _, triage_id     = AGENTS["triage"]
    _, diagnosis_id  = AGENTS["diagnosis"]
    _, validator_id  = AGENTS["validator"]
    _, comms_id      = AGENTS["comms"]
    _, postmortem_id = AGENTS["postmortem"]

    # ── STEP 1: Triage ───────────────────────────────────────────────────
    print("[Orchestrator] → Triage Agent")
    after = _send(client, "triage",
                  f"New incident alert — please triage:\n{json.dumps(alert, indent=2)}")
    raw = _poll(client, triage_id, after, timeout=90)
    if raw is None:
        return {"error": "Triage Agent timed out"}
    try:
        results["triage"] = _extract_json(raw)
    except Exception:
        results["triage"] = {"raw": raw}
    print(f"[Orchestrator] ← Triage: severity={results['triage'].get('severity','?')}")
    _post_summary(client, format_triage(results["triage"]))

    # ── STEP 2: Diagnosis ────────────────────────────────────────────────
    print("[Orchestrator] → Diagnosis Agent")
    after = _send(client, "diagnosis",
                  f"Triage complete. Diagnose root cause.\n"
                  f"Triage: {json.dumps(results['triage'])}\n"
                  f"Logs: {json.dumps(logs)}\n"
                  f"Deploys: {json.dumps(deploys)}")
    raw = _poll(client, diagnosis_id, after, timeout=120)
    if raw is None:
        return {"error": "Diagnosis Agent timed out"}
    try:
        results["diagnosis"] = _extract_json(raw)
    except Exception:
        results["diagnosis"] = {"raw": raw}
    conf = results["diagnosis"].get("confidence", 0)
    print(f"[Orchestrator] ← Diagnosis: confidence={conf}%")
    _post_summary(client, format_diagnosis(results["diagnosis"]))

    # ── STEP 3: Validator (up to 2 rounds) ──────────────────────────────
    for round_num in range(1, 3):
        print(f"[Orchestrator] → Validator (round {round_num})")
        after = _send(client, "validator",
                      f"Review this diagnosis (round {round_num}):\n"
                      f"{json.dumps(results['diagnosis'])}")
        raw = _poll(client, validator_id, after, timeout=90)
        if raw is None:
            print("[Orchestrator]   Validator timed out — proceeding")
            break
        try:
            vr = _extract_json(raw)
        except Exception:
            vr = {"verdict": "APPROVED", "feedback": raw}

        results[f"validator_round_{round_num}"] = vr
        verdict = vr.get("verdict", "APPROVED")
        print(f"[Orchestrator] ← Validator: {verdict}")
        _post_summary(client, format_validator(vr, round_num))

        if verdict == "APPROVED":
            break

        # Challenge — ask Diagnosis to revise
        print("[Orchestrator] → Diagnosis Agent (revision)")
        after = _send(client, "diagnosis",
                      f"Validator challenge (round {round_num}): {vr.get('feedback','')}\n"
                      f"Please revise your diagnosis.")
        raw = _poll(client, diagnosis_id, after, timeout=120)
        if raw:
            try:
                results["diagnosis"] = _extract_json(raw)
            except Exception:
                pass
        conf = results["diagnosis"].get("confidence", 0)
        print(f"[Orchestrator] ← Diagnosis revised: confidence={conf}%")
        _post_summary(client, format_diagnosis(results["diagnosis"]))
        if conf >= 85:
            break

    # ── STEP 4: Escalation check ─────────────────────────────────────────
    if results["diagnosis"].get("escalate"):
        reason = results["diagnosis"].get("escalation_reason", "Unknown")
        print(f"[Orchestrator] ⚠ ESCALATION: {reason}")
        results["escalation"] = {"triggered": True, "reason": reason}
        _post_summary(client, format_escalation(results["diagnosis"]))
    else:
        results["escalation"] = {"triggered": False, "reason": None}

    # ── STEP 5: Comms ────────────────────────────────────────────────────
    print("[Orchestrator] → Comms Agent")
    after = _send(client, "comms",
                  f"Incident confirmed. Generate communications.\n"
                  f"Triage: {json.dumps(results['triage'])}\n"
                  f"Diagnosis: {json.dumps(results['diagnosis'])}")
    raw = _poll(client, comms_id, after, timeout=90)
    if raw:
        try:
            results["comms"] = _extract_json(raw)
        except Exception:
            results["comms"] = {"raw": raw}
        internal_msg, external_msg = format_comms(results["comms"])
        _post_summary(client, internal_msg)
        _post_summary(client, external_msg)
    print("[Orchestrator] ← Comms done")

    # ── STEP 6: Postmortem ───────────────────────────────────────────────
    print("[Orchestrator] → Postmortem Agent")
    after = _send(client, "postmortem",
                  f"Incident resolved. Generate full postmortem.\n"
                  f"Triage: {json.dumps(results.get('triage', {}))}\n"
                  f"Diagnosis: {json.dumps(results.get('diagnosis', {}))}\n"
                  f"Comms: {json.dumps(results.get('comms', {}))}\n"
                  f"Escalation: {json.dumps(results.get('escalation', {}))}")
    raw = _poll(client, postmortem_id, after, timeout=180)
    if raw:
        postmortem_md = re.sub(r"^@\S+\s*", "", raw.strip())
        results["postmortem_report"] = postmortem_md
        with open("postmortem_output.md", "w", encoding="utf-8") as f:
            f.write(postmortem_md)
    print("[Orchestrator] ← Postmortem done")

    print("[Orchestrator] Incident response complete.")
    return results


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "mock_data/incident_payload.json"
    with open(path) as f:
        payload = json.load(f)
    results = run_incident(payload)
    printable = {k: v for k, v in results.items() if k != "postmortem_report"}
    print(json.dumps(printable, indent=2))
    if "postmortem_report" in results:
        print("\nPostmortem saved to postmortem_output.md")
