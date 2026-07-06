"""
Backtest harness: replays every synthetic historical incident in
data/incidents.json through the full Argus triage pipeline and scores
it against the labeled ground truth. This is what turns "I built an AI
SRE demo" into "I built an AI SRE demo and measured it" — the numbers
this script prints are the ones referenced in the README and the
resume/interview guide.

Methodology (deliberately simple and stated up front, not hidden):
  - RCA accuracy: does Argus's predicted failure category match the
    labeled ground-truth category?
  - Action accuracy: does the proposed runbook action match the
    labeled correct action?
  - Simulated MTTR: each incident carries a hand-estimated
    `baseline_mttr_minutes` (how long a manual on-call diagnosis +
    fix realistically takes for that failure class, based on common
    industry MTTR figures for the category). Argus's simulated MTTR
    is modeled as:
        - correct diagnosis + safe auto-remediation -> ~3 minutes
        - correct diagnosis + action escalated for human approval
          -> human still has to act, but skips the diagnosis phase
          -> ~35% of baseline (floor 5 min)
        - correct diagnosis + no action needed (false-alarm case)
          -> ~2 minutes to confirm and stand down
        - WRONG diagnosis -> modeled as slightly worse than the
          manual baseline (110%), since a wrong AI hypothesis can
          send a responder down the wrong path before they fall back
          to manual investigation. This is intentionally not rigged
          in Argus's favor.
  This is a transparent, back-of-envelope model for a portfolio
  project, not a production SLA claim — and the script says so.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tabulate import tabulate  # noqa: E402

from argus import data_store, triage_agent  # noqa: E402

os.environ.setdefault("ARGUS_AUTO_APPROVE_LOW_RISK", "1")


def run_backtest(verbose: bool = True) -> dict:
    rows = []
    for incident_id in data_store.list_incident_ids():
        incident = data_store.get_incident(incident_id)
        truth = incident["ground_truth"]

        result = triage_agent.run_triage(incident_id, auto_execute=True, notify=False)
        rca = result["rca"]
        remediation_plan = result["remediation"]
        execution = result["execution"]

        correct_rca = rca["category"] == truth["category"]
        correct_action = remediation_plan["action_id"] == truth["correct_action"]
        baseline_mttr = truth["baseline_mttr_minutes"]
        ai_mttr = _estimate_ai_mttr(
            correct_rca, correct_action, execution, baseline_mttr
        )

        rows.append(
            {
                "incident_id": incident_id,
                "service": incident["service"],
                "predicted_category": rca["category"],
                "true_category": truth["category"],
                "correct_rca": correct_rca,
                "predicted_action": remediation_plan["action_id"],
                "true_action": truth["correct_action"],
                "correct_action": correct_action,
                "confidence": rca.get("confidence", 0),
                "reasoning_source": rca.get("reasoning_source"),
                "execution_status": execution["status"],
                "baseline_mttr": baseline_mttr,
                "ai_mttr": ai_mttr,
            }
        )

    summary = _summarize(rows)
    if verbose:
        _print_report(rows, summary)
    return {"rows": rows, "summary": summary}


def _estimate_ai_mttr(
    correct_rca: bool, correct_action: bool, execution: dict, baseline: float
) -> float:
    if not correct_rca:
        return round(baseline * 1.10, 1)
    if execution["status"] == "executed":
        return 3.0
    if execution["status"] == "no_action_taken":
        return 2.0
    if execution["status"] == "escalated_for_human_approval":
        return round(max(5.0, baseline * 0.35), 1)
    return round(baseline * 1.10, 1)


def _summarize(rows: list[dict]) -> dict:
    n = len(rows)
    rca_correct = sum(r["correct_rca"] for r in rows)
    action_correct = sum(r["correct_action"] for r in rows)
    auto_executed = sum(r["execution_status"] == "executed" for r in rows)
    mean_baseline = sum(r["baseline_mttr"] for r in rows) / n
    mean_ai = sum(r["ai_mttr"] for r in rows) / n
    mttr_reduction_pct = (1 - mean_ai / mean_baseline) * 100

    return {
        "n_incidents": n,
        "rca_accuracy_pct": round(100 * rca_correct / n, 1),
        "action_match_pct": round(100 * action_correct / n, 1),
        "auto_remediated_pct": round(100 * auto_executed / n, 1),
        "mean_baseline_mttr_min": round(mean_baseline, 1),
        "mean_ai_assisted_mttr_min": round(mean_ai, 1),
        "simulated_mttr_reduction_pct": round(mttr_reduction_pct, 1),
    }


def _print_report(rows: list[dict], summary: dict) -> None:
    table = [
        [
            r["incident_id"],
            r["service"],
            f"{r['predicted_category']}{'✓' if r['correct_rca'] else ' ✗ (' + r['true_category'] + ')'}",
            f"{r['confidence']:.2f}",
            r["reasoning_source"],
            f"{r['predicted_action']}{'✓' if r['correct_action'] else ' ✗ (' + r['true_action'] + ')'}",
            r["execution_status"],
            r["baseline_mttr"],
            r["ai_mttr"],
        ]
        for r in rows
    ]
    headers = [
        "Incident",
        "Service",
        "Predicted Category",
        "Conf.",
        "Source",
        "Action",
        "Exec Status",
        "Baseline MTTR",
        "AI MTTR",
    ]
    print(tabulate(table, headers=headers, tablefmt="github"))
    print()
    print("=== Backtest Summary ===")
    for k, v in summary.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    run_backtest()
