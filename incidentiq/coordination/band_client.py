"""
band_client.py — Hybrid Band coordination layer.

Each agent posts its output to the real Band room (human-visible in the Band UI)
while the local band_history.json serves as the reliable inter-agent coordination
store that pipeline.py reads. Band events are fire-and-forget — any network failure
is silently ignored so the pipeline is never blocked.
"""

import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from thenvoi_rest import RestClient, ChatEventRequest

load_dotenv()

HISTORY_FILE = "band_history.json"
BAND_REST_URL = os.getenv("BAND_REST_URL", "https://app.band.ai")
BAND_ROOM_ID = os.getenv("BAND_ROOM_ID", "")

_AGENT_KEYS: dict[str, str] = {
    "triage_agent":    os.getenv("BAND_TRIAGE_API_KEY", ""),
    "diagnosis_agent": os.getenv("BAND_DIAGNOSIS_API_KEY", ""),
    "comms_agent":     os.getenv("BAND_COMMS_API_KEY", ""),
    "postmortem_agent":os.getenv("BAND_POSTMORTEM_API_KEY", ""),
}


def _make_client(api_key: str) -> RestClient:
    return RestClient(api_key=api_key, base_url=BAND_REST_URL)


def _band_event(api_key: str, message_type: str, content: str, metadata: dict | None = None) -> None:
    """Post one event to the Band room. Silently swallows all errors."""
    if not api_key or not BAND_ROOM_ID:
        return
    try:
        client = _make_client(api_key)
        client.agent_api_events.create_agent_chat_event(
            BAND_ROOM_ID,
            event=ChatEventRequest(
                content=content,
                message_type=message_type,
                metadata=metadata,
            ),
        )
    except Exception:
        pass


def reset_band_history() -> None:
    """Clear local coordination state and post a run-separator to Band."""
    with open(HISTORY_FILE, "w") as f:
        json.dump([], f)

    triage_key = _AGENT_KEYS.get("triage_agent", "")
    _band_event(
        triage_key,
        message_type="thought",
        content="=== New IncidentIQ pipeline run started ===",
    )


def post_to_band(agent_name: str, content: dict) -> None:
    """
    Append agent output to local coordination history, then mirror to Band as a
    tool_result event so it's visible in the Band room UI.
    """
    history = read_band_history()
    history.append({
        "agent": agent_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "content": content,
    })
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

    api_key = _AGENT_KEYS.get(agent_name, "")
    scalar_fields = {k: v for k, v in content.items() if isinstance(v, (str, int, float, bool))}
    summary = json.dumps(scalar_fields, ensure_ascii=False)
    if len(summary) > 300:
        summary = summary[:297] + "..."
    _band_event(
        api_key,
        message_type="tool_result",
        content=f"[{agent_name}] {summary}",
        metadata=content,
    )


def read_band_history() -> list:
    """Return the full agent coordination history from local state."""
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE) as f:
        return json.load(f)
