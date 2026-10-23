"""Sentinel MCP server: exposes Sentinel incidents as voice-friendly tools."""
import os
import sys
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import httpx
from mcp.server import MCPServer

BASE_URL = os.getenv("SENTINEL_URL", "http://localhost:8000")
USER = os.getenv("SENTINEL_MCP_USER", "mcp_viewer")
PASSWORD = os.getenv("SENTINEL_MCP_PASSWORD")
if not PASSWORD:
    sys.exit("Set SENTINEL_MCP_PASSWORD (and optionally SENTINEL_MCP_USER) first")

CLOSED_STATES = {"resolved", "closed", "false_positive"}
HIDDEN_TYPES = {"transaction", "combined"}  # legacy rows from before transactions were removed

mcp = MCPServer(
    "sentinel",
    version="0.1.0",
    instructions=(
        "Security analyst for Sentinel. Reads live incidents and explains why they were "
        "flagged. Scores run 0-100: 25+ MEDIUM, 50+ HIGH, 75+ CRITICAL. Keep spoken "
        "answers short and lead with the most serious incident."
    ),
)

_client = httpx.Client(base_url=BASE_URL, timeout=10, follow_redirects=True)
_lock = threading.Lock()
_token = None


def _login():
    global _token
    r = _client.post("/auth/login", json={"username": USER, "password": PASSWORD})
    r.raise_for_status()
    _token = r.json()["access_token"]


def _get(path, **params):
    with _lock:
        if _token is None:
            _login()
        for attempt in (1, 2):
            r = _client.get(path, params=params, headers={"Authorization": f"Bearer {_token}"})
            if r.status_code == 401 and attempt == 1:
                _login()
                continue
            break
    r.raise_for_status()
    return r.json()


def _incidents(limit=100, min_score=0):
    data = _get("/incidents", limit=limit, min_score=min_score)
    items = data["incidents"] if isinstance(data, dict) else data
    return [i for i in items if i.get("event_type") not in HIDDEN_TYPES]


def _ts(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _flags(inc):
    raw = inc.get("reason_flags", inc.get("reasons", []))
    if isinstance(raw, str):
        raw = [p for p in raw.split("|") if p]
    return raw


def _brief(inc):
    ctx = inc.get("context") or {}
    return {
        "id": inc.get("id"),
        "level": inc.get("alert_level"),
        "score": inc.get("risk_score"),
        "user": ctx.get("username", "unknown"),
        "ip": ctx.get("ip_address", "unknown"),
        "state": inc.get("state", "open"),
        "time": inc.get("timestamp"),
        "top_reason": (_flags(inc) or ["none recorded"])[0],
    }


def _recent(hours):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return [i for i in _incidents() if (t := _ts(i.get("timestamp"))) and t >= cutoff]


@mcp.tool()
def ping() -> str:
    """Check that the Sentinel MCP server is up."""
    return "pong"


@mcp.tool()
def get_open_incidents(min_score: int = 0, limit: int = 5) -> dict:
    """List unresolved security incidents, newest first. Use min_score=75 for critical only."""
    items = [i for i in _incidents(min_score=min_score)
             if i.get("state", "open") not in CLOSED_STATES]
    return {"total_open": len(items), "incidents": [_brief(i) for i in items[:limit]]}


@mcp.tool()
def explain_incident(incident_id: int) -> dict:
    """Explain why one incident was flagged: its score, severity and every reason."""
    try:
        inc = _get(f"/incidents/{incident_id}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": f"No incident with id {incident_id}"}
        raise
    return {**_brief(inc), "reasons": _flags(inc)}


@mcp.tool()
def summarize_recent(hours: int = 1) -> dict:
    """Summarize incidents over the last N hours: counts by severity and the most serious one."""
    items = _recent(hours)
    by_level = defaultdict(int)
    for i in items:
        by_level[i.get("alert_level", "UNKNOWN")] += 1
    worst = max(items, key=lambda i: i.get("risk_score", 0), default=None)
    return {"hours": hours, "total": len(items), "by_level": dict(by_level),
            "most_serious": _brief(worst) if worst else None}


@mcp.tool()
def top_risky_users(hours: int = 24, limit: int = 3) -> dict:
    """Rank users by risk over the last N hours."""
    stats = {}
    for i in _recent(hours):
        user = (i.get("context") or {}).get("username", "unknown")
        s = stats.setdefault(user, {"user": user, "incidents": 0, "max_score": 0})
        s["incidents"] += 1
        s["max_score"] = max(s["max_score"], i.get("risk_score", 0))
    ranked = sorted(stats.values(), key=lambda s: (s["max_score"], s["incidents"]), reverse=True)
    return {"hours": hours, "users": ranked[:limit]}


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8765)
