"""
app.py — FastAPI server exposing IncidentIQ's pipeline via HTTP.
Run with: uvicorn app:app --reload
"""

from typing import Any, Dict

from fastapi import Body, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pipeline import run_pipeline

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
    Accepts an incident payload (same shape as incident_payload.json),
    runs the full 4-agent pipeline, and returns all agent outputs plus
    the coordination feed.
    """
    result = run_pipeline(payload)
    result.pop("_report", None)  # internal field; not part of API response
    return result


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
