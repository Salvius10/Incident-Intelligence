"""
app.py — FastAPI server exposing IncidentIQ's pipeline via HTTP.
Run with: uvicorn app:app --reload

/trigger-incident uses the async Band orchestrator (band_agents/orchestrator.py).
The 5 listener agents must already be running (start with: python launcher.py).
Falls back to the synchronous pipeline if the Band orchestrator is unavailable.
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
    Triggers the full incident response.
    Runs via the Band multi-agent orchestrator (requires listener agents running).
    """
    from band_agents.orchestrator import run_incident
    return run_incident(payload)


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
