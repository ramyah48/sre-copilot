"""
Mocked observability backend.

In a real deployment these functions would call Prometheus/Alertmanager,
a log store (Loki/ELK), a deploy tracker (GitHub Actions/Argo CD), and a
status-page aggregator. Here they read from data/incidents.json so the
whole project is runnable and demoable without any real infrastructure
or credentials. Swapping the bodies of these functions for real API
calls is the only change needed to point Argus at a real stack.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "incidents.json"

_cache: list[dict[str, Any]] | None = None


def _load() -> list[dict[str, Any]]:
    global _cache
    if _cache is None:
        with open(_DATA_PATH, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def list_incident_ids() -> list[str]:
    return [inc["id"] for inc in _load()]


def get_incident(incident_id: str) -> dict[str, Any]:
    for inc in _load():
        if inc["id"] == incident_id:
            return inc
    raise KeyError(f"Unknown incident id: {incident_id}")


def list_active_alerts() -> list[dict[str, Any]]:
    """Simulates an Alertmanager/PagerDuty 'currently firing' feed."""
    alerts = []
    for inc in _load():
        alerts.append(
            {
                "incident_id": inc["id"],
                "service": inc["service"],
                **inc["alert"],
            }
        )
    return alerts


def get_metrics(incident_id: str) -> dict[str, Any]:
    return get_incident(incident_id)["metrics"]


def get_logs(incident_id: str) -> list[str]:
    return get_incident(incident_id)["logs"]


def get_recent_deploy(incident_id: str) -> dict[str, Any] | None:
    return get_incident(incident_id).get("recent_deploy")


def get_dependency_status(incident_id: str) -> dict[str, Any] | None:
    return get_incident(incident_id).get("dependency_status")
