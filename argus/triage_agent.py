"""End-to-end orchestration: the actual "agent loop" that ties together
correlation, RCA, remediation, and notification for a single incident.

This is the function both the MCP server and the backtest/demo scripts
call — it is the single source of truth for "what does Argus do when
an alert fires."
"""

from __future__ import annotations

from typing import Any

from . import correlation, notifier, rca_engine, remediation


def run_triage(incident_id: str, auto_execute: bool = True, notify: bool = True) -> dict[str, Any]:
    context = correlation.build_incident_context(incident_id)
    rca = rca_engine.propose_rca(context)
    remediation_plan = remediation.propose_remediation(context, rca)

    execution = (
        remediation.execute_remediation(remediation_plan, approved=False)
        if auto_execute
        else {"status": "not_attempted", "message": "auto_execute=False"}
    )

    summary_text = notifier.format_incident_summary(context, rca, remediation_plan, execution)
    notification_result = notifier.post_incident_summary(summary_text) if notify else None

    return {
        "context": context,
        "rca": rca,
        "remediation": remediation_plan,
        "execution": execution,
        "notification": notification_result,
        "summary_text": summary_text,
    }
