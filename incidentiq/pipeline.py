"""
pipeline.py — Core IncidentIQ orchestration logic.
Runs the 4-agent sequence through the Band coordination layer.
Importable by both main.py (CLI) and app.py (FastAPI) with no side effects.
"""

from band.band_client import reset_band_history, post_to_band, read_band_history
from agents.triage_agent import run_triage_agent
from agents.diagnosis_agent import run_diagnosis_agent
from agents.comms_agent import run_comms_agent
from agents.postmortem_agent import run_postmortem_agent


def _find(history: list, agent: str) -> dict:
    return next(e["content"] for e in history if e["agent"] == agent)


def _extract_summary(report: str) -> str:
    in_summary = False
    lines = []
    for line in report.splitlines():
        if line.strip().lower().startswith("## summary"):
            in_summary = True
            continue
        if in_summary:
            if line.strip().startswith("#"):
                break
            if line.strip():
                lines.append(line.strip())
    return " ".join(lines)


def run_pipeline(payload: dict) -> dict:
    """
    Runs Triage → Diagnosis → Comms → Postmortem against `payload`.
    Every agent output is posted to the Band coordination layer.
    Returns a dict with all outputs, escalation info, and the band feed.
    """
    reset_band_history()

    # [1/4] Triage
    triage_output = run_triage_agent(payload["alert"])
    post_to_band("triage_agent", triage_output)

    # [2/4] Diagnosis — pull triage context from Band
    history = read_band_history()
    triage_ctx = _find(history, "triage_agent")
    diagnosis_output = run_diagnosis_agent(
        payload["logs"],
        payload["deploy_history"],
        triage_ctx,
    )
    post_to_band("diagnosis_agent", diagnosis_output)

    # Escalation check
    escalation = {"triggered": False, "reason": None}
    if diagnosis_output.get("escalate"):
        reason = diagnosis_output.get("escalation_reason")
        severity = triage_output.get("severity")
        escalation = {"triggered": True, "reason": reason}
        post_to_band("system", {
            "type": "escalation",
            "reason": reason,
            "severity": severity,
        })

    # [3/4] Comms — pull triage + diagnosis from Band
    history = read_band_history()
    triage_ctx = _find(history, "triage_agent")
    diagnosis_ctx = _find(history, "diagnosis_agent")
    comms_output = run_comms_agent(triage_ctx, diagnosis_ctx)
    post_to_band("comms_agent", comms_output)

    # [4/4] Postmortem — pull all three from Band
    history = read_band_history()
    triage_ctx = _find(history, "triage_agent")
    diagnosis_ctx = _find(history, "diagnosis_agent")
    comms_ctx = _find(history, "comms_agent")
    report = run_postmortem_agent(triage_ctx, diagnosis_ctx, comms_ctx)

    with open("postmortem_output.md", "w", encoding="utf-8") as f:
        f.write(report)

    postmortem_summary = _extract_summary(report)
    post_to_band("postmortem_agent", {
        "report_saved": "postmortem_output.md",
        "summary": postmortem_summary,
    })

    band_feed = [
        {"agent": e["agent"], "timestamp": e["timestamp"]}
        for e in read_band_history()
    ]

    return {
        "triage": triage_output,
        "diagnosis": diagnosis_output,
        "comms": comms_output,
        "postmortem_summary": postmortem_summary,
        "postmortem_file": "postmortem_output.md",
        "escalation": escalation,
        "band_feed": band_feed,
        "_report": report,  # kept for main.py terminal preview; not in API response
    }
