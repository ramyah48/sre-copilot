# Argus — AI SRE Incident Triage & RCA Copilot (MCP Plugin)

**Live demo (no install, works in any browser):** https://ramyah48.github.io/sre-copilot/
*(goes live once GitHub Pages is enabled on this repo — see "Publishing the live demo" below)*

Argus is an AI SRE copilot, shipped as an **MCP (Model Context Protocol) plugin**, that watches for firing alerts, automatically correlates logs/metrics/deploys/dependency status into a single incident context, proposes a root-cause hypothesis with evidence, recommends a concrete runbook fix, and — only for pre-approved low-risk actions — executes it. Everything else is escalated to a human with the diagnosis already done.

Because it's an MCP plugin rather than a standalone dashboard, any MCP-compatible agent (Claude Desktop, Claude Code, Cowork, or a custom Claude Agent SDK app) can attach to it and answer questions like *"what's on fire right now, and what would you do about INC-004?"* in plain English.

This mirrors the "AI SRE" category that PagerDuty, Datadog (Bits AI), and incident.io have all shipped agents into over the last year — vendors report **40–60% MTTR reductions** from this pattern (autonomous diagnosis + human-approved remediation). This project is a from-scratch implementation of the same idea, sized for a portfolio.

## Why this design

| Design choice | Reasoning |
|---|---|
| MCP plugin, not a web app | Plugs directly into the agent ecosystem people already use (Claude Desktop/Code/Cowork) instead of yet another dashboard. |
| Hybrid heuristic + LLM RCA engine | The LLM path (Claude) gives open-ended reasoning over novel failures; the heuristic path is a deterministic fallback if the LLM call fails, times out, or hallucinates — so the copilot degrades gracefully instead of going dark during an incident. |
| Risk-tiered remediation gate | **The action's risk tier decides auto-execution, not the model's confidence.** A confident LLM can still be wrong; a human-set risk policy can't be talked out of its job. Medium/high-risk actions (failover, credential rotation, connection-pool surgery) always require explicit human approval — no exceptions, enforced in code, tested. |
| Synthetic incident dataset + backtest harness | Real Prometheus/PagerDuty/Slack access isn't available in a portfolio context, so Argus ships with 15 hand-labeled synthetic incidents spanning bad deploys, memory leaks, DB pool exhaustion, dependency outages, disk/cert/DNS/queue/cache/secrets/network failures, and one deliberate false alarm (legitimate traffic growth) — so accuracy and MTTR-impact can be *measured*, not just asserted. |

## Architecture

```
 Alert fires (Alertmanager/PagerDuty)
            │
            ▼
   ┌─────────────────┐
   │  data_store.py   │  mocked observability backend
   │  (swap for real  │  (metrics, logs, deploys, dep. status)
   │   Prometheus/    │
   │   PagerDuty APIs)│
   └────────┬─────────┘
            ▼
   ┌─────────────────┐
   │ correlation.py   │  builds one incident context bundle
   └────────┬─────────┘  + cheap explainable pre-correlation notes
            ▼
   ┌─────────────────┐
   │  rca_engine.py   │  Claude (LLM) reasoning ──fallback──▶ heuristic rules
   └────────┬─────────┘  returns: category, root cause, confidence, evidence
            ▼
   ┌─────────────────┐
   │ remediation.py   │  maps category → runbook action + risk tier
   └────────┬─────────┘
            ▼
   ┌─────────────────┐
   │  risk gate       │  risk=low/none + auto-approve on → execute (dry-run)
   │                  │  risk=medium/high → ALWAYS escalate for human approval
   └────────┬─────────┘
            ▼
   ┌─────────────────┐
   │  notifier.py     │  posts formatted summary to Slack (or console)
   └──────────────────┘

   server.py wraps all of the above as MCP tools (list_active_alerts,
   propose_root_cause, propose_fix, execute_fix, triage_incident, …)
```

## Publishing the live demo (so anyone with the link can try it — no install)

`docs/index.html` is a **self-contained, dependency-free reimplementation of the correlation + heuristic RCA + remediation risk-gate + backtest logic in vanilla JavaScript**, using the same 15 labeled incidents. It runs entirely in the visitor's browser — no server, no API key, no Python. Cross-checked against the Python backtest output (`node` harness) and the two agree to within floating-point rounding.

To make it live at `https://ramyah48.github.io/sre-copilot/`:

1. Push this repo to GitHub as `sre-copilot` (exact name matters for the URL above — see "Push to GitHub" below).
2. On GitHub: **Settings → Pages → Build and deployment → Source: "Deploy from a branch"** → Branch: `main`, Folder: `/docs` → **Save**.
3. Wait ~1 minute, then visit the URL above — it updates automatically on every push to `main`.

This gives you two links for your resume/LinkedIn: the **live demo** (click and try it, zero setup) and the **source repo** (the real Python implementation, MCP server, and tests behind it).

## Push to GitHub

```bash
cd sre-copilot
git init
git add .
git commit -m "Initial commit: Argus AI SRE copilot"
git branch -M main
git remote add origin https://github.com/ramyah48/sre-copilot.git
git push -u origin main
```

Then follow "Publishing the live demo" above to turn on Pages.

## Repo layout

```
sre-copilot/
├── argus/
│   ├── data_store.py     # mocked observability backend (swap for real APIs)
│   ├── correlation.py    # builds the incident context bundle
│   ├── rca_engine.py     # LLM RCA + heuristic fallback engine
│   ├── remediation.py    # runbook catalog + risk-gated execution
│   ├── notifier.py       # Slack-style incident summaries
│   ├── triage_agent.py   # end-to-end orchestration
│   └── server.py         # MCP server exposing everything as agent tools
├── data/incidents.json   # 15 hand-labeled synthetic incidents (ground truth)
├── docs/index.html       # public, no-install browser demo (GitHub Pages serves this)
├── eval/backtest.py      # replays all incidents, scores accuracy + simulated MTTR
├── tests/test_argus.py   # pytest suite (34 tests): rules, risk gate, pipeline
├── demo.py               # `python demo.py` or `python demo.py --trace INC-004`
└── RESUME_AND_INTERVIEW_GUIDE.md
```

## Quickstart

```bash
pip install -r requirements.txt

# Full backtest across all 15 synthetic incidents (works with zero setup):
python demo.py

# Step-by-step trace of one incident (great for a live interview demo):
python demo.py --trace INC-004

# Run the test suite:
pytest -q

# Run it as an MCP plugin (attach from Claude Desktop/Code/Cowork):
python -m argus.server
```

Optional: copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY` to switch the RCA engine from heuristic mode to real Claude reasoning. Set `SLACK_WEBHOOK_URL` to post real Slack messages instead of printing to console.

## Actual backtest results (measured, not aspirational)

```
n_incidents: 15
rca_accuracy_pct: 100.0
action_match_pct: 100.0
auto_remediated_pct: 60.0
mean_baseline_mttr_min: 40.3
mean_ai_assisted_mttr_min: 8.2
simulated_mttr_reduction_pct: 79.6
```

**Honest caveat, worth saying out loud (including in an interview):** the heuristic ruleset was authored against this same 15-incident set, so 100% RCA accuracy in heuristic mode is accuracy *on the training set*, not a claim about generalization — it's a regression baseline, not a benchmark. The methodology (`eval/backtest.py` docstring) is deliberately transparent about this. The parts of the project that generalize are the *architecture* (hybrid reasoning, correlation-before-reasoning, risk-tiered execution) and the LLM reasoning path, which reasons over the raw context bundle the same way it would for a novel incident it's never seen. A natural next step (see Roadmap) is a held-out incident set to test true generalization of the LLM path.

## Roadmap / what I'd build next

- Swap `data_store.py` for real Prometheus + Alertmanager + a log backend (Loki) — the interface is already shaped for this.
- Held-out eval set (incidents never seen while writing the heuristic rules) to measure true LLM-mode generalization instead of heuristic-mode memorization.
- Vector-search over a runbook/postmortem knowledge base so RCA can cite *"this matches postmortem #47 from March"* instead of only pattern-matching logs.
- A lightweight web UI for approving/rejecting medium/high-risk remediations instead of a `--approved` CLI flag.
