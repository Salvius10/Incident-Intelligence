"""
setup_band.py — One-time setup: create a shared Band room for all 4 IncidentIQ agents.

Run once before using the Band integration:
    python setup_band.py

After running, copy the printed BAND_ROOM_ID value into your .env file.
"""

import os
import sys

from dotenv import load_dotenv
from thenvoi_rest import RestClient, ChatRoomRequest, ParticipantRequest

load_dotenv()

BAND_REST_URL = os.getenv("BAND_REST_URL", "https://app.band.ai")
BAND_TRIAGE_API_KEY = os.getenv("BAND_TRIAGE_API_KEY", "")

SIBLING_AGENTS = [
    ("diagnosis_agent", os.getenv("BAND_DIAGNOSIS_AGENT_ID", "")),
    ("comms_agent", os.getenv("BAND_COMMS_AGENT_ID", "")),
    ("postmortem_agent", os.getenv("BAND_POSTMORTEM_AGENT_ID", "")),
]


def main():
    if not BAND_TRIAGE_API_KEY:
        print("ERROR: BAND_TRIAGE_API_KEY not set in .env")
        sys.exit(1)

    print(f"Connecting to Band at {BAND_REST_URL} ...")
    client = RestClient(api_key=BAND_TRIAGE_API_KEY, base_url=BAND_REST_URL)

    try:
        me = client.agent_api_identity.get_agent_me()
        print(f"Authenticated as: {me.data.name}  id={me.data.id}")
    except Exception as e:
        print(f"ERROR: Authentication failed: {e}")
        sys.exit(1)

    print("\nCreating shared IncidentIQ room (triage agent as owner) ...")
    try:
        room_response = client.agent_api_chats.create_agent_chat(chat=ChatRoomRequest())
        room_id = room_response.data.id
        print(f"Room created:  id={room_id}")
    except Exception as e:
        print(f"ERROR: Could not create room: {e}")
        sys.exit(1)

    print("\nAdding sibling agents as participants ...")
    for agent_name, agent_id in SIBLING_AGENTS:
        if not agent_id:
            print(f"  SKIP  {agent_name}: BAND_*_AGENT_ID not set in .env")
            continue
        try:
            client.agent_api_participants.add_agent_chat_participant(
                room_id,
                participant=ParticipantRequest(participant_id=agent_id),
            )
            print(f"  OK    {agent_name}  ({agent_id})")
        except Exception as e:
            print(f"  ERROR {agent_name}: {e}")

    print("\n" + "=" * 60)
    print("Setup complete. Add this line to your .env file:")
    print(f"BAND_ROOM_ID={room_id}")
    print("=" * 60)


if __name__ == "__main__":
    main()
