"""
app.py — FastAPI server exposing IncidentIQ's pipeline via HTTP.
Run with: uvicorn app:app --reload

/trigger-incident sends the payload to the Band Orchestrator Agent via a
single @mention message. All subsequent coordination happens over WebSocket.
The 6 Band agents must already be running (start with: python launcher.py).
"""

from typing import Any, Dict

from fastapi import Body, FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="IncidentIQ")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/trigger-incident")
def trigger_incident(payload: Dict[str, Any] = Body(...)):
    """
    Sends the incident payload to the Band Orchestrator Agent.
    All coordination happens over Band WebSocket — no REST polling.
    Requires all 6 Band agents to be running (python launcher.py).
    """
    from band_agents.orchestrator import send_trigger
    send_trigger(payload)
    return {"status": "triggered", "message": "Incident sent to Band Orchestrator Agent."}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/postmortem")
async def get_postmortem():
    from fastapi.responses import PlainTextResponse
    try:
        with open("postmortem_output.md", encoding="utf-8") as f:
            return PlainTextResponse(f.read(), media_type="text/markdown")
    except FileNotFoundError:
        return PlainTextResponse(
            "Postmortem not yet generated. Run the pipeline first.", status_code=404
        )
