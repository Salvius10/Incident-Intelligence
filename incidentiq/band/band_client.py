"""
band_client.py — Local Band-shaped coordination layer.

TODO: Replace internals with real Band SDK/API calls once Band account
access is confirmed (pending Discord response). When swapped:
- post_to_band() would call Band's message-send endpoint for the
  appropriate agent_id in a shared room
- read_band_history() would call Band's room history endpoint
Function signatures (post_to_band, read_band_history) must stay identical
so no other files need to change.
"""

import json
import os
from datetime import datetime, timezone

HISTORY_FILE = "band_history.json"


def reset_band_history():
    """Clears the history file at the start of a new incident run."""
    with open(HISTORY_FILE, "w") as f:
        json.dump([], f)


def post_to_band(agent_name: str, content: dict) -> None:
    """Appends a message from an agent to the shared history."""
    history = read_band_history()
    history.append({
        "agent": agent_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "content": content,
    })
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def read_band_history() -> list:
    """Returns the full message history, empty list if file doesn't exist."""
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE) as f:
        return json.load(f)
