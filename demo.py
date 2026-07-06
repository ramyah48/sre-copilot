#!/usr/bin/env python3
"""
Single entry point for demoing Argus without any setup:

    python demo.py                 # run the full backtest across all 15 incidents
    python demo.py --trace INC-004 # print a full step-by-step trace for one incident

No API keys or external services are required — Argus falls back to a
deterministic heuristic RCA engine and prints "Slack" messages to the
console. Set ANTHROPIC_API_KEY in your environment (see .env.example)
to see the LLM-powered reasoning mode instead.
"""

from __future__ import annotations

import argparse
import json
import sys

from argus import triage_agent
from eval.backtest import run_backtest


def print_trace(incident_id: str) -> None:
    result = triage_agent.run_triage(incident_id, auto_execute=True, notify=True)

    print(f"\n=== STEP 1: Correlated incident context for {incident_id} ===")
    print(json.dumps(result["context"], indent=2))

    print("\n=== STEP 2: RCA hypothesis ===")
    print(json.dumps(result["rca"], indent=2))

    print("\n=== STEP 3: Proposed remediation ===")
    print(json.dumps(result["remediation"], indent=2))

    print("\n=== STEP 4: Execution result ===")
    print(json.dumps(result["execution"], indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Argus AI SRE demo runner")
    parser.add_argument("--trace", metavar="INCIDENT_ID", help="Print a full trace for one incident (e.g. INC-004)")
    args = parser.parse_args()

    if args.trace:
        print_trace(args.trace)
    else:
        run_backtest()


if __name__ == "__main__":
    sys.exit(main())
