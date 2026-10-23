#!/usr/bin/env python3
"""Alexa+ simulation bridge for Sentinel.

Serves index.html and exposes POST /api/ask {"text": "..."}.
It picks an MCP tool with keyword rules (no LLM), calls your MCP server over
Streamable HTTP the same way scripts/mcp_call.sh does, and returns the result
plus a sentence to speak. Standard library only.

Run from the repo root:  python3 voice_demo/bridge.py
Then open:               http://127.0.0.1:8800
"""
import json
import os
import re
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:8765/mcp")
PORT = int(os.environ.get("VOICE_PORT", "8800"))
HERE = Path(__file__).resolve().parent
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "MCP-Protocol-Version": "2025-11-25",
}


# ---------- MCP client (mirrors scripts/mcp_call.sh) ----------
def _post(body, sid=None):
    h = dict(HEADERS)
    if sid:
        h["mcp-session-id"] = sid
    req = urllib.request.Request(MCP_URL, json.dumps(body).encode(), h, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.headers.get("mcp-session-id"), r.read().decode()


def _parse(raw):
    for line in raw.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return json.loads(raw) if raw.strip() else None


def call_tool(name, args):
    sid, _ = _post({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                   "clientInfo": {"name": "alexa-sim", "version": "0"}},
    })
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    _, raw = _post({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": name, "arguments": args},
    }, sid)
    msg = _parse(raw)
    if not msg or "result" not in msg:
        raise RuntimeError(f"MCP error: {msg}")
    result = msg["result"]
    text = result["content"][0]["text"] if result.get("content") else ""
    if result.get("isError"):
        raise RuntimeError(text or "tool returned an error")
    try:
        return json.loads(text)
    except ValueError:
        return text


# ---------- keyword routing (stands in for Alexa+'s own model) ----------
def route(text):
    t = text.lower()
    num = re.search(r"\b(\d{1,9})\b", t)
    hours = 24
    m = re.search(r"(\d+)\s*(?:hour|hr)", t)
    if m:
        hours = int(m.group(1))
    if num and re.search(r"explain|why|detail|tell me about", t):
        return "explain_incident", {"incident_id": int(num.group(1))}
    if re.search(r"risk|user|who|account", t):
        return "top_risky_users", {"hours": hours, "limit": 5}
    if re.search(r"summar|overview|what happened|how many|recent|report", t):
        return "summarize_recent", {"hours": hours}
    if re.search(r"critical|urgent|severe|serious|high", t):
        return "get_open_incidents", {"min_score": 75, "limit": 5}
    if re.search(r"incident|alert|open|threat|attack", t):
        return "get_open_incidents", {"limit": 5}
    if re.search(r"ping|status|alive|online|up\b|working", t):
        return "ping", {}
    return None, None


# ---------- spoken answer ----------
def _find_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return v
    return None


def _scalars(d, limit=6):
    parts = []
    for k, v in d.items():
        if isinstance(v, (str, int, float)) and not isinstance(v, bool):
            parts.append(f"{k.replace('_', ' ')} {v}")
        if len(parts) >= limit:
            break
    return ", ".join(parts)


def speech_for(tool, args, data):
    if tool == "ping":
        return "The Sentinel server is up and responding."
    if tool == "explain_incident":
        if isinstance(data, dict) and "level" in data:
            reasons = data.get("reasons") or []
            return (f"Incident {data.get('id')} is {str(data['level']).lower()}, "
                    f"score {int(data.get('score', 0))}, for user {data.get('user')}. "
                    f"It was flagged for {len(reasons)} reasons. "
                    f"The main one: {data.get('top_reason')}.")
        return "I could not find that incident."
    items = _find_list(data)
    if tool == "get_open_incidents":
        crit = args.get("min_score", 0) >= 75
        label = "critical " if crit else ""
        if not items:
            return f"There are no open {label}incidents right now."
        top = items[0]
        who = top.get("user", "an unknown user")
        why = top.get("top_reason") or top.get("reason") or "multiple risk signals"
        return (f"Here are the {len(items)} newest open {label}incidents. "
                f"The latest is {str(top.get('level', '')).lower()} for {who}: {why}.")
    if tool == "top_risky_users":
        if not items:
            return "I found no risky users in that period."
        names = [str(i.get("user") or i.get("name") or i.get("username"))
                 for i in items[:3] if isinstance(i, dict)]
        return f"The riskiest users over the last {args['hours']} hours are " + ", ".join(names) + "."
    if tool == "summarize_recent":
        body = _scalars(data) if isinstance(data, dict) else str(data)
        return f"Here is the summary for the last {args['hours']} hours. {body}"
    return "Done."


# ---------- HTTP ----------
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/ask":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            text = json.loads(self.rfile.read(n))["text"]
            tool, args = route(text)
            if not tool:
                return self._send(200, {
                    "tool": None, "args": None, "data": None,
                    "speech": "Sorry, I can help with incidents, summaries, risky users and explaining an incident by number."})
            data = call_tool(tool, args)
            self._send(200, {"tool": tool, "args": args, "data": data,
                             "speech": speech_for(tool, args, data)})
        except Exception as e:  # keep the demo alive and show the reason
            self._send(502, {"error": str(e),
                             "speech": "I could not reach the Sentinel server."})

    def log_message(self, fmt, *a):
        print("[bridge]", fmt % a)


if __name__ == "__main__":
    print(f"Alexa+ simulation on http://127.0.0.1:{PORT}  ->  MCP {MCP_URL}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()