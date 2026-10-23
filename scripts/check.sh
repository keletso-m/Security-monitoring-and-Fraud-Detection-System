#!/usr/bin/env bash
# scripts/check.sh - one-command health + MCP spec conformance check.
# Run with the servers up (scripts/dev.sh start). Start the voice bridge too
# (python3 voice_demo/bridge.py) if you want it checked; otherwise it is skipped.
cd "$(dirname "$0")/.." || exit 1

URL=${MCP_URL:-http://127.0.0.1:8765/mcp}
API=${API_URL:-http://127.0.0.1:8000}
BRIDGE=${BRIDGE_URL:-http://127.0.0.1:8800}
CT='Content-Type: application/json'
ACC='Accept: application/json, text/event-stream'
PV='MCP-Protocol-Version: 2025-11-25'
INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"check","version":"0"}}}'
pass=0; fail=0

report() {  # name expected actual
  if [ "$2" = "$3" ]; then echo "PASS  $1 (got $3)"; pass=$((pass+1))
  else echo "FAIL  $1 (expected $2, got $3)"; fail=$((fail+1)); fi
}
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$@"; }
sse_json() { python3 -c "
import sys, json
raw = sys.stdin.read()
for line in raw.splitlines():
    if line.startswith('data:'):
        raw = line[5:].strip(); break
print(json.dumps(json.loads(raw)))" 2>/dev/null; }

echo "== Services =="
report "API /health" 200 "$(code "$API/health")"

echo; echo "== MCP session (Streamable HTTP, spec 2025-11-25) =="
HDR=$(mktemp)
ic=$(curl -s -D "$HDR" -o /dev/null -w '%{http_code}' --max-time 10 -X POST "$URL" -H "$CT" -H "$ACC" -H "$PV" --data "$INIT")
SID=$(grep -i '^mcp-session-id' "$HDR" | awk '{print $2}' | tr -d '\r'); rm -f "$HDR"
report "initialize" 200 "$ic"
report "session id issued" yes "$([ -n "$SID" ] && echo yes || echo no)"
report "initialized notification (spec 202)" 202 "$(code -X POST "$URL" -H "$CT" -H "$ACC" -H "$PV" -H "mcp-session-id: $SID" --data '{"jsonrpc":"2.0","method":"notifications/initialized"}')"

echo; echo "== Spec rules =="
TL='{"jsonrpc":"2.0","id":3,"method":"tools/list"}'
report "bad Origin rejected (spec 403, DNS-rebinding)" 403 "$(code -X POST "$URL" -H "$CT" -H "$ACC" -H "$PV" -H "mcp-session-id: $SID" -H 'Origin: http://evil.example' --data "$TL")"
report "bad protocol version (spec 400)" 400 "$(code -X POST "$URL" -H "$CT" -H "$ACC" -H 'MCP-Protocol-Version: 1999-01-01' -H "mcp-session-id: $SID" --data "$TL")"
report "missing session id (spec 400)" 400 "$(code -X POST "$URL" -H "$CT" -H "$ACC" -H "$PV" --data "$TL")"
report "unknown session id (spec 404)" 404 "$(code -X POST "$URL" -H "$CT" -H "$ACC" -H "$PV" -H 'mcp-session-id: nope' --data "$TL")"

echo; echo "== Tools =="
TOOLS=$(curl -s --max-time 10 -X POST "$URL" -H "$CT" -H "$ACC" -H "$PV" -H "mcp-session-id: $SID" --data "$TL" | sse_json \
  | python3 -c "import sys,json; print(' '.join(sorted(t['name'] for t in json.load(sys.stdin)['result']['tools'])))" 2>/dev/null)
report "tools/list" "explain_incident get_open_incidents ping summarize_recent top_risky_users" "$TOOLS"
CALL=$(curl -s --max-time 15 -X POST "$URL" -H "$CT" -H "$ACC" -H "$PV" -H "mcp-session-id: $SID" \
  --data '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"get_open_incidents","arguments":{"limit":1}}}' | sse_json \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['isError'])" 2>/dev/null)
report "tools/call get_open_incidents isError" False "$CALL"

echo; echo "== Voice bridge =="
if [ "$(code "$BRIDGE/")" = "200" ]; then
  T=$(curl -s --max-time 20 -X POST "$BRIDGE/api/ask" -H "$CT" --data '{"text":"any critical incidents?"}' \
      | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool'))" 2>/dev/null)
  report "bridge routes 'any critical incidents?'" get_open_incidents "$T"
else
  echo "SKIP  bridge not running (python3 voice_demo/bridge.py)"
fi

echo; echo "== Repo hygiene =="
LEAK=$(git ls-files | grep -E '(^|/)\.env$|\.db$|^logs/')
report "no secrets/databases/logs tracked" none "${LEAK:-none}"
report "working tree clean" clean "$([ -z "$(git status --short)" ] && echo clean || echo dirty)"

echo; echo "== Unit tests (informational) =="
venv/bin/python -m pytest tests -q 2>&1 | tail -3

echo; echo "Result: $pass passed, $fail failed"
[ "$fail" -eq 0 ]