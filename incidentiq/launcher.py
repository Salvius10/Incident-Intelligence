"""
launcher.py — Starts all 5 listener agents as subprocesses, then runs the Orchestrator.

Usage:
    python launcher.py [scenario]
    scenario: 1 (default), 2 (memory leak), 3 (third-party outage)
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import time

BASE_DIR = Path(__file__).resolve().parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

AGENT_FILES = [
    "band_agents/triage_agent.py",
    "band_agents/diagnosis_agent.py",
    "band_agents/validator_agent.py",
    "band_agents/comms_agent.py",
    "band_agents/postmortem_agent.py",
]

SCENARIOS = {
    "1": "mock_data/incident_payload.json",
    "2": "mock_data/incident_payload_memory_leak.json",
    "3": "mock_data/incident_payload_third_party.json",
}


def shutdown_processes(processes, show_output=False):
    print("\nShutting down agent listeners...")
    for _, p in processes:
        if p.poll() is None:
            p.terminate()
    for name, p in processes:
        out = ""
        try:
            out, _ = p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            out, _ = p.communicate()
        if show_output and out:
            print(f"\n{name} output:\n{out[:4000]}")
    print("Done.")


def main():
    scenario = sys.argv[1] if len(sys.argv) > 1 else "1"
    payload_path = SCENARIOS.get(scenario, SCENARIOS["1"])

    print(f"IncidentIQ — Scenario {scenario}: {payload_path}")
    print("Starting 5 listener agents...")

    processes = []
    child_env = os.environ.copy()
    child_env.setdefault("PYTHONIOENCODING", "utf-8")
    for agent_file in AGENT_FILES:
        p = subprocess.Popen(
            [sys.executable, str(BASE_DIR / agent_file)],
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=child_env,
        )
        processes.append((agent_file, p))
        print(f"  Started {agent_file}  (pid {p.pid})")

    results = {}
    try:
        print("Waiting 8s for agents to connect to Band WebSocket...")
        time.sleep(8)

        # Check for early crashes
        for name, p in processes:
            if p.poll() is not None:
                out, _ = p.communicate()
                print(f"  WARNING: {name} exited early:\n{out[:4000]}")

        print("\nRunning Orchestrator...")
        from band_agents.orchestrator import run_incident

        with open(BASE_DIR / payload_path) as f:
            payload = json.load(f)

        results = run_incident(payload)

        print("\n" + "=" * 60)
        print("INCIDENT RESPONSE COMPLETE")
        print("=" * 60)
        printable = {k: v for k, v in results.items() if k != "postmortem_report"}
        print(json.dumps(printable, indent=2, ensure_ascii=False))
        if "postmortem_report" in results:
            print("\nPostmortem saved to postmortem_output.md")
    finally:
        shutdown_processes(processes, show_output=bool(results.get("error")))


if __name__ == "__main__":
    main()
