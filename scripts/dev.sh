#!/usr/bin/env bash
# usage: scripts/dev.sh start|stop|status   (start needs SENTINEL_MCP_PASSWORD exported)
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
case "$1" in
  start)
    if [ -z "$SENTINEL_MCP_PASSWORD" ]; then echo "export SENTINEL_MCP_PASSWORD first"; exit 1; fi
    PYTHONPATH=$(pwd) nohup venv/bin/uvicorn app.main:app > logs/api.out 2>&1 &
    echo "waiting for API..."
    for i in $(seq 1 30); do curl -s localhost:8000/health > /dev/null && break; sleep 1; done
    nohup venv-mcp/bin/python sentinel_mcp/server.py > logs/mcp.out 2>&1 &
    PYTHONPATH=$(pwd) nohup venv/bin/python simulator/live.py --interval 2 > logs/sim.out 2>&1 &
    sleep 2; echo started ;;
  stop)
    pkill -f "uvicorn app.main:app"; pkill -f sentinel_mcp/server.py; pkill -f simulator/live.py; echo stopped ;;
  status)
    ss -ltnp 2>/dev/null | grep -E ':8000|:8765' || echo "nothing listening"
    pgrep -af "simulator/live.py" || echo "simulator not running" ;;
  *) echo "usage: $0 start|stop|status" ;;
esac
