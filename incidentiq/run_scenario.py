"""
run_scenario.py — Run the IncidentIQ pipeline against a specific mock payload.
Usage: python run_scenario.py mock_data/incident_payload_memory_leak.json
"""

import json
import sys
import textwrap

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from pipeline import run_pipeline

SEP    = "-" * 60
HEAVY  = "=" * 60
INDENT = "                 "


def _wrap(text, indent=INDENT):
    lines = textwrap.wrap(str(text), width=60)
    return ("\n" + indent).join(lines)


def _fmt_ts(iso):
    try:
        return iso.split("T")[1][:8] + "Z"
    except Exception:
        return iso


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_scenario.py <path/to/payload.json>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)

    print(HEAVY)
    print(f"INCIDENTIQ — SCENARIO: {path}")
    print(HEAVY)

    result     = run_pipeline(payload)
    triage     = result["triage"]
    diagnosis  = result["diagnosis"]
    comms      = result["comms"]
    escalation = result["escalation"]
    band_feed  = result["band_feed"]
    report     = result["_report"]

    # [1/4] Triage
    print("\n[1/4] TRIAGE AGENT")
    print(SEP)
    print(f"Severity:        {triage.get('severity')}")
    print(f"Affected:        {', '.join(triage.get('affected_systems', []))}")
    print(f"Regions:         {', '.join(triage.get('regions', []))}")
    print(f"Users impacted:  {triage.get('users_impacted', 0):,}")
    print(f"Business impact: {triage.get('business_impact')}")
    print(f"Summary:         {_wrap(triage.get('summary', ''))}")

    # [2/4] Diagnosis
    print("\n[2/4] DIAGNOSIS AGENT")
    print(SEP)
    culprit     = diagnosis.get("culprit", {})
    culprit_str = f"{culprit.get('deploy_id')} — {culprit.get('detail')}"
    print(f"Root cause:      {_wrap(diagnosis.get('root_cause_hypothesis', ''))}")
    print(f"Confidence:      {diagnosis.get('confidence')}%")
    print(f"Culprit:         {_wrap(culprit_str)}")
    print(f"Fix direction:   {_wrap(diagnosis.get('fix_direction', ''))}")
    print(f"Escalate:        {'Yes' if escalation['triggered'] else 'No'}")
    if escalation["triggered"]:
        print(f"Escalation reason: {_wrap(escalation.get('reason', ''))}")

    # Escalation alert block
    if escalation["triggered"]:
        reason   = escalation.get("reason", "No reason provided")
        severity = triage.get("severity", "UNKNOWN")
        print()
        print(f"⚠️  {HEAVY}")
        print(f"⚠️  HUMAN ESCALATION TRIGGERED")
        print(f"⚠️  {HEAVY}")
        print(f"⚠️  Reason: {reason}")
        print(f"⚠️  Severity: {severity}")
        print(f"⚠️  An on-call engineer should be notified immediately.")
        print(f"⚠️  {HEAVY}")

    # [3/4] Comms
    print("\n[3/4] COMMS AGENT")
    print(SEP)
    print("Internal Slack message:")
    print(textwrap.fill(comms.get("internal_slack_message", ""), width=60,
                        initial_indent="  ", subsequent_indent="  "))
    print()
    print("Status page update:")
    print(textwrap.fill(comms.get("status_page_update", ""), width=60,
                        initial_indent="  ", subsequent_indent="  "))

    # [4/4] Postmortem
    print("\n[4/4] POSTMORTEM AGENT")
    print(SEP)
    preview = report.splitlines()[:3]
    print(f"Postmortem saved to postmortem_output.md ({len(report)} chars)")
    print("Preview:")
    for line in preview:
        print(f"  {line}")

    # Coordination Feed
    print()
    print(HEAVY)
    print("COORDINATION FEED (chronological)")
    print(HEAVY)
    for i, entry in enumerate(band_feed, 1):
        print(f"[{i}] {entry['agent']:<22} @ {_fmt_ts(entry['timestamp'])}")
    print(HEAVY)

    print()
    print(HEAVY)
    print("PIPELINE COMPLETE")
    print(HEAVY)


if __name__ == "__main__":
    main()
