"""
Signal correlation: joins the alert with metrics, logs, recent deploys,
and dependency status into a single "incident context bundle".

This is the step that turns scattered telemetry into something an LLM
(or a human) can reason over in one pass, instead of having to jump
between five different dashboards.
"""

from __future__ import annotations

from typing import Any

from . import data_store


def build_incident_context(incident_id: str) -> dict[str, Any]:
    incident = data_store.get_incident(incident_id)

    context = {
        "incident_id": incident_id,
        "service": incident["service"],
        "alert": incident["alert"],
        "metrics": data_store.get_metrics(incident_id),
        "logs": data_store.get_logs(incident_id),
        "recent_deploy": data_store.get_recent_deploy(incident_id),
        "dependency_status": data_store.get_dependency_status(incident_id),
    }

    context["correlation_notes"] = _correlation_notes(context)
    return context


def _correlation_notes(context: dict[str, Any]) -> list[str]:
    """Cheap, explainable correlation heuristics computed before any
    LLM call — these are surfaced as extra evidence for the RCA engine
    and make the final hypothesis auditable rather than a black box.
    """
    notes = []

    deploy = context.get("recent_deploy")
    if deploy and deploy.get("minutes_before_alert", 999) <= 15:
        notes.append(
            f"A deploy (version {deploy['version']}) shipped "
            f"{deploy['minutes_before_alert']} minutes before this alert fired — "
            "strong temporal correlation with a bad release."
        )

    dep = context.get("dependency_status")
    if dep and "degraded" in str(dep.get("status", "")).lower():
        notes.append(
            f"Upstream dependency '{dep['name']}' is independently reported as "
            "degraded — this service may just be a victim, not the source."
        )

    metrics = context.get("metrics", {})
    if metrics.get("cpu_pct", 0) < 30 and metrics.get("error_rate_pct", 0) > 5:
        notes.append(
            "Error rate is elevated while CPU is low — points away from resource "
            "exhaustion and toward a logic/config/dependency bug."
        )
    if metrics.get("cpu_pct", 0) > 80:
        notes.append(
            "CPU is saturated — resource exhaustion or noisy-neighbor contention is plausible."
        )

    if not notes:
        notes.append(
            "No strong automatic correlation found; relying on log/metric pattern matching."
        )

    return notes
