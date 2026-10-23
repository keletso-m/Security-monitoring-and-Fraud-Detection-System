#!/usr/bin/env bash
# usage: scripts/mcp_call.sh <tool> '<json-arguments>'
URL=${MCP_URL:-http://127.0.0.1:8765/mcp}
ARGS="$2"; [ -z "$ARGS" ] && ARGS='{}'
H=(-H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -H 'MCP-Protocol-Version: 2025-11-25')
SID=$(curl -s -i -X POST "$URL" "${H[@]}" --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}' | grep -i '^mcp-session-id' | awk '{print $2}' | tr -d '\r')
curl -s -X POST "$URL" "${H[@]}" -H "mcp-session-id: $SID" --data '{"jsonrpc":"2.0","method":"notifications/initialized"}' > /dev/null
curl -s -X POST "$URL" "${H[@]}" -H "mcp-session-id: $SID" --data "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"$1\",\"arguments\":$ARGS}}" | sed -n 's/^data: //p' | python3 -m json.tool
