"""
Argus MCP server.

Exposes the incident-triage toolchain as an MCP (Model Context Protocol)
plugin so ANY MCP-compatible AI agent — Claude Desktop, Claude Code,
Cowork, or a custom Claude Agent SDK app — can be pointed at a live (or,
here, simulated) production environment and reason about incidents in
natural language, e.g.:

    "What's currently on fire, and what would you do about INC-004?"

Run directly for local testing:
    python -m argus.server

Or register it as an MCP plugin in Claude Desktop / Claude Code by
pointing the config at this file with `python -m argus.server` as the
launch command (see README.md).
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from . import correlation, data_store, notifier, rca_engine, remediation, triage_agent

mcp = FastMCP("argus-sre")


@mcp.tool()
def list_active_alerts() -> list[dict[str, Any]]:
    """List all currently firing alerts across every monitored service."""
    return data_store.list_active_alerts()


@mcp.tool()
def get_incident_context(incident_id: str) -> dict[str, Any]:
    """Get the fully correlated context bundle (alert + metrics + logs +
    recent deploys + dependency status) for one incident."""
    return correlation.build_incident_context(incident_id)


@mcp.tool()
def propose_root_cause(incident_id: str) -> dict[str, Any]:
    """Run RCA reasoning over an incident and return a structured root
    cause hypothesis with confidence and evidence."""
    context = correlation.build_incident_context(incident_id)
    return rca_engine.propose_rca(context)


@mcp.tool()
def propose_fix(incident_id: str) -> dict[str, Any]:
    """Propose a concrete remediation/runbook action for an incident,
    including its risk tier and whether it needs human approval."""
    context = correlation.build_incident_context(incident_id)
    rca = rca_engine.propose_rca(context)
    return remediation.propose_remediation(context, rca)


@mcp.tool()
def execute_fix(incident_id: str, approved: bool = False) -> dict[str, Any]:
    """Execute the proposed remediation for an incident. Low-risk actions
    may auto-execute depending on server config; medium/high risk actions
    ALWAYS require approved=True from a human."""
    context = correlation.build_incident_context(incident_id)
    rca = rca_engine.propose_rca(context)
    plan = remediation.propose_remediation(context, rca)
    return remediation.execute_remediation(plan, approved=approved)


@mcp.tool()
def triage_incident(incident_id: str, auto_execute: bool = True, notify: bool = True) -> dict[str, Any]:
    """Run the full Argus triage pipeline for one incident end-to-end:
    correlate signals -> propose RCA -> propose remediation -> execute
    (if safe) -> post an incident summary. Returns the full trace."""
    return triage_agent.run_triage(incident_id, auto_execute=auto_execute, notify=notify)


@mcp.tool()
def list_known_incidents() -> list[str]:
    """List the incident IDs available in this environment (useful for
    demos / exploring what Argus can see)."""
    return data_store.list_incident_ids()


if __name__ == "__main__":
    mcp.run()
