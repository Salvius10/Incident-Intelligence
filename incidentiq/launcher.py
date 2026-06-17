"""
launcher.py — Starts all 5 listener agents as subprocesses, then runs the Orchestrator.

Usage:
    python launcher.py [scenario]
    scenario: 1 (default), 2 (memory leak), 3 (third-party outage)
"""

import json
import os
import subprocess
import sys
import time

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


def main():
    scenario = sys.argv[1] if len(sys.argv) > 1 else "1"
    payload_path = SCENARIOS.get(scenario, SCENARIOS["1"])

    print(f"IncidentIQ — Scenario {scenario}: {payload_path}")
    print("Starting 5 listener agents...")

    processes = []
    for agent_file in AGENT_FILES:
        p = subprocess.Popen(
            [sys.executable, agent_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        processes.append((agent_file, p))
        print(f"  Started {agent_file}  (pid {p.pid})")

    print("Waiting 8s for agents to connect to Band WebSocket...")
    time.sleep(8)

    # Check for early crashes
    for name, p in processes:
        if p.poll() is not None:
            out, _ = p.communicate()
            print(f"  WARNING: {name} exited early:\n{out.decode(errors='replace')[:500]}")

    print("\nRunning Orchestrator...")
    from band_agents.orchestrator import run_incident

    with open(payload_path) as f:
        payload = json.load(f)

    results = run_incident(payload)

    print("\n" + "=" * 60)
    print("INCIDENT RESPONSE COMPLETE")
    print("=" * 60)
    printable = {k: v for k, v in results.items() if k != "postmortem_report"}
    print(json.dumps(printable, indent=2, ensure_ascii=False))
    if "postmortem_report" in results:
        print("\nPostmortem saved to postmortem_output.md")

    print("\nShutting down agent listeners...")
    for _, p in processes:
        p.terminate()
    for _, p in processes:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()

    print("Done.")


if __name__ == "__main__":
    main()
