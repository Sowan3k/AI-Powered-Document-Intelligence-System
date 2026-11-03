#!/usr/bin/env bash
# Container entry point.
#   ./start.sh          migrations, then API and worker together (Render, one container)
#   ./start.sh api      migrations, then API only (docker-compose)
#   ./start.sh worker   worker only (docker-compose)
# If either process exits, the script stops the other and exits, so the
# platform restarts the whole container.
set -euo pipefail

MODE="${1:-all}"
PORT="${PORT:-8000}"

run_migrations() {
  if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "start.sh: running database migrations"
    alembic upgrade head
  fi
}

UVICORN_ARGS=(app.main:app --host 0.0.0.0 --port "$PORT"
  --proxy-headers --forwarded-allow-ips="*" --no-server-header)

case "$MODE" in
  api)
    run_migrations
    exec uvicorn "${UVICORN_ARGS[@]}"
    ;;
  worker)
    exec python -m app.worker.main
    ;;
  all)
    run_migrations
    python -m app.worker.main &
    WORKER_PID=$!
    uvicorn "${UVICORN_ARGS[@]}" &
    API_PID=$!

    STOPPING=0
    stop_all() {
      kill -TERM "$API_PID" "$WORKER_PID" 2>/dev/null || true
    }
    on_signal() {
      STOPPING=1
      stop_all
    }
    trap on_signal TERM INT

    # Wait until either process exits or a stop signal arrives.
    set +e
    wait -n "$API_PID" "$WORKER_PID"
    STATUS=$?
    set -e
    if [ "$STOPPING" = "1" ]; then
      wait || true
      exit 0
    fi
    # A process ended on its own. That is always a failure, even with status 0.
    echo "start.sh: a process exited with status $STATUS, stopping the rest" >&2
    stop_all
    wait || true
    if [ "$STATUS" = "0" ]; then STATUS=1; fi
    exit "$STATUS"
    ;;
  *)
    echo "usage: start.sh [all|api|worker]" >&2
    exit 2
    ;;
esac
