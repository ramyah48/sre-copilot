"""Formats and posts incident summaries. Uses a real Slack incoming
webhook if SLACK_WEBHOOK_URL is set, otherwise prints to stdout so the
project is fully demoable without any external accounts."""

from __future__ import annotations

import os
from typing import Any


def format_incident_summary(
    context: dict[str, Any],
    rca: dict[str, Any],
    remediation: dict[str, Any],
    execution: dict[str, Any],
) -> str:
    evidence = "\n".join(f"  • {e}" for e in rca.get("evidence", []))
    lines = [
        f"*[Argus AI SRE] {context['incident_id']} — {context['alert']['alertname']}* ({context['service']})",
        f"Severity: {context['alert'].get('severity', 'unknown')}",
        "",
        f"*Root cause hypothesis* (confidence {rca.get('confidence', 0):.0%}, via {rca.get('reasoning_source', 'n/a')}):",
        f"  {rca.get('root_cause', 'n/a')}",
        "Evidence:",
        evidence,
        "",
        f"*Proposed action*: {remediation['description']} (risk: {remediation['risk']})",
        f"*Execution result*: {execution['status']} — {execution['message']}",
    ]
    return "\n".join(lines)


def post_incident_summary(message: str) -> dict[str, Any]:
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if webhook_url:
        import requests

        resp = requests.post(webhook_url, json={"text": message}, timeout=5)
        return {"status": "posted_to_slack", "http_status": resp.status_code}

    print("\n----- [SIMULATED SLACK POST] -----")
    print(message)
    print("-----------------------------------\n")
    return {"status": "printed_to_console"}
