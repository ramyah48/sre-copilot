"""
Root-cause-analysis engine.

Two reasoning modes, chosen automatically:

1. LLM mode (if ANTHROPIC_API_KEY is set): sends the correlated incident
   context bundle to Claude and asks for a structured RCA hypothesis.
2. Heuristic mode (default / fallback): a small rule-based keyword
   classifier. This keeps the whole project runnable offline, and — just
   as important in production — gives Argus a deterministic fallback if
   the LLM call fails, times out, or returns malformed output. Real AI
   SRE systems lean on this kind of hybrid design rather than trusting
   a single LLM call for a page-worthy decision.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

_SYSTEM_PROMPT = """You are Argus, an AI Site Reliability Engineer performing \
incident root-cause analysis. You will be given a correlated bundle of \
alert metadata, metrics, logs, recent deploys, and dependency status for \
one incident. Respond with ONLY a JSON object with these exact keys:

{
  "category": one short snake_case label for the failure class,
  "root_cause": one or two sentences explaining the most likely root cause,
  "confidence": a number from 0.0 to 1.0,
  "evidence": a list of 2-4 short strings citing the specific signals that support your hypothesis,
  "severity_assessment": "low" | "medium" | "high" | "critical"
}

Be specific and cite the evidence you were given. Do not include any text outside the JSON object."""


def propose_rca(context: dict[str, Any]) -> dict[str, Any]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            return _propose_rca_llm(context, api_key)
        except Exception as exc:  # noqa: BLE001 - deliberate broad fallback
            result = _propose_rca_heuristic(context)
            result["llm_error"] = f"{type(exc).__name__}: {exc}"
            return result
    return _propose_rca_heuristic(context)


def _propose_rca_llm(context: dict[str, Any], api_key: str) -> dict[str, Any]:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": "Incident context bundle:\n\n" + json.dumps(context, indent=2),
            }
        ],
    )
    raw_text = "".join(block.text for block in message.content if hasattr(block, "text"))
    parsed = _extract_json(raw_text)
    parsed["reasoning_source"] = "llm"
    return parsed


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {text!r}")
    return json.loads(match.group(0))


# ---------------------------------------------------------------------------
# Heuristic fallback engine
# ---------------------------------------------------------------------------

# Ordered rules: (category, matcher_fn, evidence_fn) — first match wins.
_RULES: list[tuple[str, Any, Any]] = []


def _rule(category, matcher, evidence):
    _RULES.append((category, matcher, evidence))


def _log_text(context):
    return " ".join(context.get("logs", [])).lower()


_rule(
    "bad_deploy",
    lambda c: c.get("recent_deploy") and c["recent_deploy"].get("minutes_before_alert", 999) <= 15,
    lambda c: [f"Deploy {c['recent_deploy']['version']} shipped {c['recent_deploy']['minutes_before_alert']}m before the alert"],
)
_rule(
    "downstream_dependency_outage",
    lambda c: c.get("dependency_status") and "degraded" in str(c["dependency_status"].get("status", "")).lower(),
    lambda c: [f"Dependency status: {c['dependency_status']['name']} reported degraded"],
)
_rule(
    "memory_leak",
    lambda c: "outofmemory" in _log_text(c) or "oomkilled" in _log_text(c) or "heap space" in _log_text(c),
    lambda c: ["Log signature: OutOfMemoryError / OOMKilled"],
)
_rule(
    "db_connection_pool_exhaustion",
    lambda c: "connection pool" in _log_text(c) or "hikaripool" in _log_text(c),
    lambda c: ["Log signature: connection pool exhausted"],
)
_rule(
    "disk_full",
    lambda c: "no space left on device" in _log_text(c) or "disk" in _log_text(c),
    lambda c: ["Log signature: No space left on device"],
)
_rule(
    "cert_expiry",
    lambda c: "certificate" in _log_text(c) or "x509" in _log_text(c),
    lambda c: ["Log signature: certificate expired / x509 error"],
)
_rule(
    "config_error",
    lambda c: "feature-flag" in _log_text(c) or "feature flag" in _log_text(c) or "flag '" in _log_text(c),
    lambda c: ["Log signature: feature flag change correlated with regression"],
)
_rule(
    "network_partition",
    lambda c: "no route to host" in _log_text(c) or "packet loss" in _log_text(c) or "cross-az" in _log_text(c) or "cross az" in c.get("alert", {}).get("alertname", "").lower(),
    lambda c: ["Log signature: no route to host / cross-AZ packet loss"],
)
_rule(
    "cache_stampede",
    lambda c: "cache" in _log_text(c) and ("hit rate" in _log_text(c) or "stampede" in _log_text(c) or "thundering" in _log_text(c) or "concurrent regeneration" in _log_text(c)),
    lambda c: ["Log signature: cache hit-rate collapse with concurrent regeneration requests"],
)
_rule(
    "dns_resolution_failure",
    lambda c: "dns" in _log_text(c) or "no such host" in _log_text(c) or "lookup" in _log_text(c),
    lambda c: ["Log signature: DNS lookup failure / no such host"],
)
_rule(
    "queue_backlog",
    lambda c: "lag" in _log_text(c) or "backlog" in _log_text(c),
    lambda c: ["Log signature: consumer lag / queue backlog growing"],
)
_rule(
    "secrets_rotation_failure",
    lambda c: ("401" in _log_text(c) or "unauthorized" in _log_text(c)) and "rotat" in _log_text(c),
    lambda c: ["Log signature: 401 Unauthorized immediately following a secret rotation event"],
)
_rule(
    "resource_exhaustion",
    lambda c: c.get("metrics", {}).get("cpu_pct", 0) > 90 or "throttl" in _log_text(c) or "noisy neighbor" in _log_text(c),
    lambda c: ["Metric signature: CPU saturation / cgroup throttling"],
)
_rule(
    "traffic_spike",
    lambda c: c.get("metrics", {}).get("error_rate_pct", 0) < 2 and "autoscaler" in _log_text(c),
    lambda c: ["Metrics show healthy error rate with autoscaler already responding to load"],
)


def _propose_rca_heuristic(context: dict[str, Any]) -> dict[str, Any]:
    for category, matcher, evidence_fn in _RULES:
        try:
            if matcher(context):
                evidence = evidence_fn(context) + context.get("correlation_notes", [])[:2]
                return {
                    "category": category,
                    "root_cause": _ROOT_CAUSE_TEMPLATES.get(
                        category, "Pattern matched known failure signature."
                    ).format(service=context.get("service", "the service")),
                    "confidence": 0.72,
                    "evidence": evidence,
                    "severity_assessment": context.get("alert", {}).get("severity", "medium"),
                    "reasoning_source": "heuristic",
                }
        except Exception:  # noqa: BLE001 - a single bad rule shouldn't crash triage
            continue

    return {
        "category": "unknown",
        "root_cause": "No heuristic rule matched this signal pattern; escalate to a human SRE for manual investigation.",
        "confidence": 0.2,
        "evidence": ["No matching log/metric signature in the heuristic rule set"],
        "severity_assessment": context.get("alert", {}).get("severity", "medium"),
        "reasoning_source": "heuristic",
    }


_ROOT_CAUSE_TEMPLATES = {
    "bad_deploy": "A recent deploy to {service} is temporally correlated with this alert and is the most likely root cause.",
    "downstream_dependency_outage": "{service} is healthy internally but blocked on a degraded upstream dependency.",
    "memory_leak": "{service} shows a memory-leak pattern (steady growth ending in OOMKill).",
    "db_connection_pool_exhaustion": "{service}'s database connection pool is exhausted, likely due to a long-running query holding connections.",
    "disk_full": "{service}'s disk is full, most likely because log/data rotation has stopped working.",
    "cert_expiry": "{service} is rejecting TLS connections because a certificate has expired.",
    "config_error": "A recent configuration or feature-flag change to {service} is causing this regression.",
    "network_partition": "{service} is affected by a network partition between availability zones, not an application bug.",
    "cache_stampede": "A cache-stampede on {service} is overloading the backend after a hot key expired.",
    "dns_resolution_failure": "{service} is failing DNS resolution for a dependency hostname, likely a stale local resolver cache.",
    "queue_backlog": "{service}'s consumers have not scaled with incoming volume, causing backlog to grow unbounded.",
    "secrets_rotation_failure": "{service} is using a stale cached credential after a secret rotation invalidated the old one.",
    "resource_exhaustion": "{service} is CPU-saturated, likely due to co-scheduled workloads contending for the same nodes.",
    "traffic_spike": "This looks like legitimate traffic growth on {service}, already being handled by autoscaling — not a failure.",
}
