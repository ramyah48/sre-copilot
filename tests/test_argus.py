"""
Unit + regression tests for Argus. Run with: pytest -q

Covers:
  - data loading integrity
  - heuristic RCA classifies each known incident category correctly
    (this is a regression test — if someone edits a rule and breaks a
    category, this fails immediately instead of silently degrading
    the backtest numbers)
  - the remediation risk gate refuses to auto-execute medium/high risk
    actions without explicit human approval, no matter what
  - the full triage pipeline runs end-to-end for every incident without
    raising
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from argus import correlation, data_store, rca_engine, remediation, triage_agent  # noqa: E402
from eval.backtest import run_backtest  # noqa: E402


def test_all_incidents_load():
    ids = data_store.list_incident_ids()
    assert len(ids) == 15
    assert len(set(ids)) == len(ids)  # unique


@pytest.mark.parametrize("incident_id", data_store.list_incident_ids())
def test_heuristic_rca_matches_ground_truth(incident_id, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # force heuristic mode
    incident = data_store.get_incident(incident_id)
    context = correlation.build_incident_context(incident_id)
    rca = rca_engine.propose_rca(context)
    assert rca["category"] == incident["ground_truth"]["category"], (
        f"{incident_id}: expected {incident['ground_truth']['category']}, got {rca['category']}"
    )


def test_high_risk_action_requires_approval():
    plan = {"action_id": "failover_to_secondary_az", "risk": "high"}
    os.environ["ARGUS_AUTO_APPROVE_LOW_RISK"] = (
        "1"  # even with auto-approve on for LOW risk
    )
    result = remediation.execute_remediation(plan, approved=False)
    assert result["status"] == "escalated_for_human_approval"


def test_low_risk_action_can_auto_execute():
    plan = {
        "action_id": "restart_service",
        "risk": "low",
        "simulated_command": "kubectl rollout restart deployment/foo",
    }
    os.environ["ARGUS_AUTO_APPROVE_LOW_RISK"] = "1"
    result = remediation.execute_remediation(plan, approved=False)
    assert result["status"] == "executed"


@pytest.mark.parametrize("incident_id", data_store.list_incident_ids())
def test_full_pipeline_runs_without_error(incident_id):
    result = triage_agent.run_triage(incident_id, auto_execute=True, notify=False)
    assert "rca" in result and "remediation" in result and "execution" in result


def test_backtest_accuracy_above_threshold():
    """Regression guard: heuristic RCA accuracy across the whole synthetic
    incident set should stay high. If a future rule change tanks this,
    the build should fail loudly rather than shipping a worse copilot."""
    os.environ.pop("ANTHROPIC_API_KEY", None)
    results = run_backtest(verbose=False)
    assert results["summary"]["rca_accuracy_pct"] >= 90.0
