# Resume & Interview Guide — Argus (AI SRE Copilot)

**Links to use everywhere (resume, LinkedIn, cover letters):**
- Live demo (click and try, no install): `https://ramyaharika-code.github.io/sre-copilot/`
- Source code: `https://github.com/ramyaharika-code/sre-copilot`

Put both on the resume line — recruiters click the live demo, engineers click the repo.

## Resume bullets

Pick 2-3 depending on space. All numbers below are pulled directly from `eval/backtest.py` output — re-run `python demo.py` before an interview to reconfirm them.

- Built **Argus**, an AI SRE incident-triage copilot shipped as an MCP (Model Context Protocol) plugin, integrating alert, metrics, log, deploy, and dependency signals into a single correlated context and using an LLM to generate root-cause hypotheses with cited evidence and confidence scores.
- Designed a **risk-tiered remediation gate** enforced in code (not by the model) so only pre-approved low-risk runbook actions (rollback, restart, cache warm, DNS flush) can auto-execute; medium/high-risk actions (failover, credential rotation, DB pool changes) always require explicit human approval — validated with automated tests.
- Built a **hybrid reasoning architecture**: LLM-based RCA with a deterministic heuristic fallback, so the system degrades gracefully instead of failing silently if the LLM call errors, times out, or returns malformed output.
- Built a **backtest harness** replaying 15 hand-labeled synthetic incidents across 14 real-world SRE failure categories (bad deploys, memory leaks, DB pool exhaustion, dependency outages, disk/cert/DNS/queue/cache/secrets failures, network partitions, and a deliberate false-alarm case) to measure RCA accuracy, action-match rate, and a modeled MTTR reduction, with the methodology and its limitations documented transparently.
- Wrote a 34-test pytest suite covering rule regressions, the remediation risk gate, and end-to-end pipeline execution — runs in <0.1s, wired for CI.

## 30-second elevator pitch

"I built an AI SRE copilot called Argus that plugs into Claude as an MCP tool. When an alert fires, it pulls together the metrics, logs, recent deploys, and dependency status into one context bundle, asks an LLM for a root-cause hypothesis with evidence, and proposes a fix from a runbook catalog. The key design decision is that the *risk tier* of the action — not the model's confidence — decides whether it auto-executes. Low-risk stuff like a rollback or restart can run automatically; anything touching credentials, failover, or infrastructure always needs a human to approve it, and that's enforced in code with tests, not just a prompt instruction. I also built a backtest harness with 15 labeled synthetic incidents so I could actually measure accuracy instead of just demoing it."

## Likely interview questions + how to answer them

**"Walk me through what happens when an alert fires."**
Alert → `correlation.py` builds one context bundle from mocked (swappable for real) metrics/logs/deploys/dependency status → `rca_engine.py` gets an LLM (or heuristic fallback) hypothesis with confidence + evidence → `remediation.py` maps the failure category to a runbook action and risk tier → the risk gate either auto-executes (dry-run) or escalates for human approval → `notifier.py` posts a formatted summary. Walk through the `--trace INC-004` output live if asked to demo — it's a dependency-outage incident that gets correctly diagnosed but correctly escalated (medium risk) rather than auto-executed.

**"How do you prevent the AI from making things worse in production?"**
This is the risk-gate answer: the LLM's confidence is never the gate — the action's risk tier is, and that's a policy set by a human, hardcoded, and covered by `test_high_risk_action_requires_approval`/`test_low_risk_action_can_auto_execute`. Even a 99%-confident hallucination can't trigger a failover or credential rotation without a human clicking approve. I'd extend this in a real system with staged rollout of auto-remediation (shadow mode → low blast-radius services → everything) the same way you'd roll out any automation.

**"What happens if the LLM call fails or is slow during an incident?"**
That's exactly why there's a heuristic fallback in `rca_engine.py` — any exception from the Anthropic call (timeout, malformed JSON, API outage) falls back to a deterministic rule-based classifier so the copilot still produces *something* actionable instead of going dark exactly when it's needed most.

**"Your backtest shows 100% RCA accuracy — isn't that suspicious?"**
Yes, and I say so directly in the README: the heuristic rules were authored against the same 15 incidents used to score them, so that's training-set accuracy, not a generalization claim — it's a regression baseline that stops me from silently breaking a rule later. The part that actually has to generalize is the LLM reasoning path, which reasons over the raw signals the same way for an incident it's never seen. Next step on my roadmap is a held-out eval set to test that properly. (Interviewers consistently respond well to "here's the limitation, here's why, here's the fix" — it reads as engineering maturity, not a weakness to hide.)

**"How would you scale this to a real environment?"**
Swap `data_store.py`'s functions for real Prometheus/Alertmanager/Loki/PagerDuty calls — nothing else in the pipeline needs to change because the interface (`get_metrics`, `get_logs`, `list_active_alerts`, etc.) is already shaped that way. Add a real approval UI instead of a CLI flag. Add a vector-searchable knowledge base of past postmortems so RCA can cite precedent, not just pattern-match current signals.

**"Why an MCP plugin instead of a standalone service?"**
Because the interesting distribution channel for this kind of tool right now is inside the agent an on-call engineer is already using (Claude Desktop/Code/Cowork), not one more tab to check. Wrapping the same logic as MCP tools means any MCP-compatible agent can ask "what's on fire?" in plain language and get grounded, tool-backed answers instead of a hallucinated guess.

**"What was the hardest part?"**
Deciding where the LLM's judgment should and shouldn't be trusted. It's easy to build something that looks impressive in a demo where the model is right; the harder design problem is what happens when it's confidently wrong, and building the risk gate + heuristic fallback so the system fails safe instead of fails impressive.

## What to say if asked "is this in production anywhere?"

Be direct: this is a portfolio project built to demonstrate the architecture and design judgment behind real AI-SRE tools (PagerDuty's SRE Agent, Datadog Bits AI, incident.io's AI SRE), not a production deployment — and be ready to talk about exactly what would need to change to get there (real integrations, staged rollout, on-call sign-off process, audit logging). Overclaiming here is the one thing to avoid; the honesty about scope is itself a signal interviewers look for.
