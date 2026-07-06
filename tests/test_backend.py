"""
Tests for the FastAPI backend. Uses FastAPI's TestClient, which calls
the app directly in-process (no real network socket needed), so these
run as fast as the rest of the suite.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("ARGUS_AUTO_APPROVE_LOW_RISK", "1")

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import _decisions, app  # noqa: E402

client = TestClient(app)


def setup_function():
    """Each test starts from a clean decision store so tests don't leak
    approval state into each other."""
    _decisions.clear()


def test_root_health_check():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_list_incidents_returns_all_15():
    resp = client.get("/incidents")
    assert resp.status_code == 200
    assert len(resp.json()) == 15


def test_trace_for_unknown_incident_is_404():
    resp = client.get("/incidents/INC-999/trace")
    assert resp.status_code == 404


def test_low_risk_incident_auto_executes_via_api():
    # INC-001 is a bad_deploy -> rollback_deploy -> low risk -> auto-executes.
    resp = client.get("/incidents/INC-001/trace")
    assert resp.status_code == 200
    body = resp.json()
    assert body["execution"]["status"] == "executed"
    assert body["approved_by"] is None  # never needed a human


def test_medium_risk_incident_requires_approval_via_api():
    # INC-004 is a downstream dependency outage -> activate_fallback_provider -> medium risk.
    resp = client.get("/incidents/INC-004/trace")
    assert resp.status_code == 200
    body = resp.json()
    assert body["execution"]["status"] == "escalated_for_human_approval"

    # Approving it should flip execution to "executed" and record who approved it.
    approve_resp = client.post(
        "/incidents/INC-004/approve", json={"approved_by": "ramya"}
    )
    assert approve_resp.status_code == 200
    approved_body = approve_resp.json()
    assert approved_body["execution"]["status"] == "executed"
    assert approved_body["approved_by"] == "ramya"
    assert approved_body["approved_at"] is not None


def test_reset_clears_stored_decision():
    client.get("/incidents/INC-004/trace")
    assert "INC-004" in _decisions
    resp = client.post("/incidents/INC-004/reset")
    assert resp.status_code == 200
    assert "INC-004" not in _decisions


def test_backtest_endpoint_matches_cli_shape():
    resp = client.get("/backtest")
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["n_incidents"] == 15
    assert "rca_accuracy_pct" in summary
    assert "simulated_mttr_reduction_pct" in summary
