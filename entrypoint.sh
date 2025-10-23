#!/usr/bin/env bash
set -e

: "${RUN_MIGRATIONS:=true}"

# export FLASK_APP if not set
export FLASK_APP=${FLASK_APP:-run.py}

if [ "$RUN_MIGRATIONS" = "true" ]; then
  echo "Running database migrations..."
  flask db upgrade || echo "migrations failed (continuing)"
fi

exec "$@"
