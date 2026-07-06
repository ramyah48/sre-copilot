"""
Runbook / remediation catalog and the safety-gated execution path.

The core design principle: **the risk tier of an action — not the LLM's
confidence — decides whether it can run automatically.** An LLM can be
persuasive and wrong; a risk policy set by a human SRE cannot be
argued out of its job. Low/none risk actions can auto-execute when
ARGUS_AUTO_APPROVE_LOW_RISK=1. Medium/high risk actions always require
an explicit human `approved=True` before `execute_remediation` will run
them, regardless of how confident the RCA was.
"""

from __future__ import annotations

import os
from typing import Any

RUNBOOK_CATALOG: dict[str, dict[str, Any]] = {
    "rollback_deploy": {
        "description": "Roll back the most recent deploy to the previous stable version.",
        "risk": "low",
        "simulated_command": "argocd app rollback {service} --to previous-stable",
    },
    "restart_service": {
        "description": "Rolling-restart the affected service's pods.",
        "risk": "low",
        "simulated_command": "kubectl rollout restart deployment/{service}",
    },
    "increase_connection_pool": {
        "description": "Temporarily raise the DB connection pool size and kill the offending long-running query.",
        "risk": "medium",
        "simulated_command": 'kubectl set env deployment/{service} DB_POOL_MAX=100 && psql -c "SELECT pg_terminate_backend(pid) ..."',
    },
    "activate_fallback_provider": {
        "description": "Fail over to the secondary payment/notification provider.",
        "risk": "medium",
        "simulated_command": "featureflag set use_secondary_provider=true --service {service}",
    },
    "clear_disk_space": {
        "description": "Clear old rotated logs/temp files and re-enable log rotation.",
        "risk": "low",
        "simulated_command": "ssh {service} 'find /var/log -mtime +2 -delete && systemctl restart logrotate.timer'",
    },
    "rotate_certificate": {
        "description": "Trigger emergency certificate re-issuance and reload the TLS terminator.",
        "risk": "medium",
        "simulated_command": "certbot renew --cert-name api.example.com --force && systemctl reload nginx",
    },
    "revert_config_flag": {
        "description": "Revert the offending feature flag to its previous value.",
        "risk": "low",
        "simulated_command": "featureflag revert search_use_new_ranker --service {service}",
    },
    "scale_out": {
        "description": "Add replicas / move workload off contended nodes.",
        "risk": "low",
        "simulated_command": "kubectl scale deployment/{service} --replicas=+3",
    },
    "failover_to_secondary_az": {
        "description": "Fail traffic away from the affected availability zone.",
        "risk": "high",
        "simulated_command": "aws elb modify-target-group --az-exclude us-east-1b",
    },
    "warm_cache": {
        "description": "Pre-warm the hot cache key and add jitter/locking to prevent re-stampede.",
        "risk": "low",
        "simulated_command": "cache-cli warm feed:trending:global --with-lock",
    },
    "flush_dns_cache": {
        "description": "Flush the local DNS resolver cache and re-resolve the dependency hostname.",
        "risk": "low",
        "simulated_command": "systemd-resolve --flush-caches",
    },
    "scale_out_consumers": {
        "description": "Add consumer instances to drain the backlog.",
        "risk": "low",
        "simulated_command": "kubectl scale deployment/{service} --replicas=+5",
    },
    "rotate_credentials": {
        "description": "Force-refresh the cached credential from the secrets manager.",
        "risk": "medium",
        "simulated_command": "vault kv get -force-refresh secret/{service}/api-key && kubectl rollout restart deployment/{service}",
    },
    "monitor_only": {
        "description": "No remediation needed; continue monitoring.",
        "risk": "none",
        "simulated_command": None,
    },
}

_AUTO_APPROVE_RISK_TIERS = {"none", "low"}


def propose_remediation(context: dict[str, Any], rca: dict[str, Any]) -> dict[str, Any]:
    """Maps an RCA category to a concrete runbook action."""
    action_id = _CATEGORY_TO_ACTION.get(rca.get("category"), "restart_service")
    runbook = RUNBOOK_CATALOG[action_id]
    requires_approval = runbook["risk"] not in _AUTO_APPROVE_RISK_TIERS

    return {
        "action_id": action_id,
        "description": runbook["description"],
        "risk": runbook["risk"],
        "requires_human_approval": requires_approval,
        "simulated_command": (runbook["simulated_command"] or "").format(
            service=context.get("service", "")
        ),
    }


def execute_remediation(
    remediation: dict[str, Any], approved: bool = False
) -> dict[str, Any]:
    """Executes (in simulation) a proposed remediation, subject to the risk gate.

    - risk == none/low: auto-executes if ARGUS_AUTO_APPROVE_LOW_RISK=1, else
      still requires `approved=True`.
    - risk == medium/high: ALWAYS requires `approved=True`, no exceptions.
    """
    auto_approve_enabled = os.environ.get("ARGUS_AUTO_APPROVE_LOW_RISK", "0") == "1"
    can_auto = remediation["risk"] in _AUTO_APPROVE_RISK_TIERS and auto_approve_enabled

    if not (approved or can_auto):
        return {
            "status": "escalated_for_human_approval",
            "message": f"Action '{remediation['action_id']}' (risk={remediation['risk']}) requires human approval before execution.",
        }

    if remediation["action_id"] == "monitor_only":
        return {
            "status": "no_action_taken",
            "message": "Confirmed non-issue; monitoring only.",
        }

    return {
        "status": "executed",
        "message": f"[DRY RUN] Would execute: {remediation['simulated_command']}",
        "auto_approved": can_auto and not approved,
    }


_CATEGORY_TO_ACTION = {
    "bad_deploy": "rollback_deploy",
    "memory_leak": "restart_service",
    "db_connection_pool_exhaustion": "increase_connection_pool",
    "downstream_dependency_outage": "activate_fallback_provider",
    "disk_full": "clear_disk_space",
    "cert_expiry": "rotate_certificate",
    "config_error": "revert_config_flag",
    "network_partition": "failover_to_secondary_az",
    "cache_stampede": "warm_cache",
    "dns_resolution_failure": "flush_dns_cache",
    "queue_backlog": "scale_out_consumers",
    "secrets_rotation_failure": "rotate_credentials",
    "resource_exhaustion": "scale_out",
    "traffic_spike": "monitor_only",
    "unknown": "restart_service",
}
