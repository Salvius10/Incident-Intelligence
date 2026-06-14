"""
main.py — IncidentIQ pipeline orchestrator.
Runs all 4 agents sequentially: Triage -> Diagnosis -> Comms -> Postmortem.
Band integration and FastAPI endpoint added in later steps.
"""

import json
import sys
import textwrap

# force UTF-8 on Windows consoles so emoji in agent output prints cleanly
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from agents.triage_agent import run_triage_agent
from agents.diagnosis_agent import run_diagnosis_agent, load_logs_and_deploys
from agents.comms_agent import run_comms_agent
from agents.postmortem_agent import run_postmortem_agent


SEP = "-" * 60
HEAVY = "=" * 60
WRAP_WIDTH = 60
INDENT = "                 "  # aligns continuation lines under value column


def _wrap(text: str, indent: str = INDENT) -> str:
    lines = textwrap.wrap(str(text), width=WRAP_WIDTH)
    return ("\n" + indent).join(lines)


def load_payload(path="mock_data/incident_payload.json"):
    with open(path) as f:
        return json.load(f)


def main():
    payload = load_payload()

    print(HEAVY)
    print("INCIDENTIQ — INCIDENT RESPONSE PIPELINE")
    print(HEAVY)

    # ------------------------------------------------------------------
    # [1/4] Triage Agent
    # ------------------------------------------------------------------
    print("\n[1/4] TRIAGE AGENT")
    print(SEP)

    triage_output = run_triage_agent(payload["alert"])

    systems = ", ".join(triage_output.get("affected_systems", []))
    regions = ", ".join(triage_output.get("regions", []))
    users   = f"{triage_output.get('users_impacted', 0):,}"

    print(f"Severity:        {triage_output.get('severity')}")
    print(f"Affected:        {systems}")
    print(f"Regions:         {regions}")
    print(f"Users impacted:  {users}")
    print(f"Business impact: {triage_output.get('business_impact')}")
    print(f"Summary:         {_wrap(triage_output.get('summary', ''))}")

    # ------------------------------------------------------------------
    # [2/4] Diagnosis Agent
    # ------------------------------------------------------------------
    print("\n[2/4] DIAGNOSIS AGENT")
    print(SEP)

    logs, deploy_history = load_logs_and_deploys()
    diagnosis_output = run_diagnosis_agent(logs, deploy_history, triage_output)

    culprit     = diagnosis_output.get("culprit", {})
    culprit_str = f"{culprit.get('deploy_id')} — {culprit.get('detail')}"
    escalate    = diagnosis_output.get("escalate", False)

    print(f"Root cause:      {_wrap(diagnosis_output.get('root_cause_hypothesis', ''))}")
    print(f"Confidence:      {diagnosis_output.get('confidence')}%")
    print(f"Culprit:         {_wrap(culprit_str)}")
    print(f"Fix direction:   {_wrap(diagnosis_output.get('fix_direction', ''))}")
    print(f"Escalate:        {'Yes' if escalate else 'No'}")

    # ------------------------------------------------------------------
    # Escalation check
    # ------------------------------------------------------------------
    if escalate:
        reason   = diagnosis_output.get("escalation_reason", "No reason provided")
        severity = triage_output.get("severity", "UNKNOWN")
        print()
        print(f"⚠️  {HEAVY}")
        print(f"⚠️  HUMAN ESCALATION TRIGGERED")
        print(f"⚠️  {HEAVY}")
        print(f"⚠️  Reason: {reason}")
        print(f"⚠️  Severity: {severity}")
        print(f"⚠️  An on-call engineer should be notified immediately.")
        print(f"⚠️  {HEAVY}")

    # ------------------------------------------------------------------
    # [3/4] Comms Agent
    # ------------------------------------------------------------------
    print("\n[3/4] COMMS AGENT")
    print(SEP)

    comms_output = run_comms_agent(triage_output, diagnosis_output)

    slack_preview  = textwrap.fill(comms_output.get("internal_slack_message", ""), width=WRAP_WIDTH, initial_indent="  ", subsequent_indent="  ")
    status_preview = textwrap.fill(comms_output.get("status_page_update", ""), width=WRAP_WIDTH, initial_indent="  ", subsequent_indent="  ")

    print("Internal Slack message:")
    print(slack_preview)
    print()
    print("Status page update:")
    print(status_preview)

    # ------------------------------------------------------------------
    # [4/4] Postmortem Agent
    # ------------------------------------------------------------------
    print("\n[4/4] POSTMORTEM AGENT")
    print(SEP)

    report = run_postmortem_agent(triage_output, diagnosis_output, comms_output)

    with open("postmortem_output.md", "w", encoding="utf-8") as f:
        f.write(report)

    preview_lines = report.splitlines()[:3]
    print(f"Postmortem saved to postmortem_output.md ({len(report)} chars)")
    print("Preview:")
    for line in preview_lines:
        print(f"  {line}")

    # ------------------------------------------------------------------
    print()
    print(HEAVY)
    print("PIPELINE COMPLETE")
    print(HEAVY)


if __name__ == "__main__":
    main()
