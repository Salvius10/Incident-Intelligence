"""
launcher.py — Starts all 6 Band agents (5 specialists + orchestrator) as
subprocesses, then fires a single trigger message to the Orchestrator via Band.
All inter-agent coordination runs over WebSocket — no REST polling loop.

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
    "band_agents/orchestrator.py",
]

SCENARIOS = {
    "1": "mock_data/incident_payload.json",
    "2": "mock_data/incident_payload_memory_leak.json",
    "3": "mock_data/incident_payload_third_party.json",
}


def shutdown_processes(processes):
    print("\nShutting down agent listeners...")
    for _, p in processes:
        if p.poll() is None:
            p.terminate()
    for name, p in processes:
        try:
            p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate()
    print("Done.")


def main():
    scenario = sys.argv[1] if len(sys.argv) > 1 else "1"
    payload_path = SCENARIOS.get(scenario, SCENARIOS["1"])

    print(f"IncidentIQ — Scenario {scenario}: {payload_path}")
    print("Starting 6 Band agents (5 specialists + orchestrator)...")

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

    try:
        print("Waiting 8s for all agents to connect to Band WebSocket...")
        time.sleep(8)

        # Check for early crashes
        for name, p in processes:
            if p.poll() is not None:
                out, _ = p.communicate()
                print(f"  WARNING: {name} exited early:\n{out[:2000]}")

        with open(BASE_DIR / payload_path) as f:
            payload = json.load(f)

        from band_agents.orchestrator import send_trigger
        send_trigger(payload)

        print("\nOrchestrator is driving the incident response through Band WebSocket.")
        print("Watch the Band room for live updates. Press Ctrl+C to stop agents.\n")

        # Keep agents alive
        while True:
            time.sleep(5)
            for name, p in processes:
                if p.poll() is not None:
                    out, _ = p.communicate()
                    print(f"  Agent {name} exited unexpectedly:\n{out[:1000]}")

    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        shutdown_processes(processes)


if __name__ == "__main__":
    main()
