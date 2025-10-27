#!/usr/bin/env bash
set -e

# export FLASK_APP if not set
export FLASK_APP=${FLASK_APP:-run.py}

# Wait for DB to be ready if DATABASE_URL is set (useful for docker-compose)
if [ -n "$DATABASE_URL" ]; then
	echo "DATABASE_URL is set, waiting for DB readiness..."
	ATTEMPTS=60
	COUNT=0
	until python - <<PY
import os, sys
try:
	import psycopg2
	dsn = os.environ.get('DATABASE_URL')
	if not dsn:
		sys.exit(1)
	conn = psycopg2.connect(dsn)
	conn.close()
	sys.exit(0)
except Exception:
	sys.exit(1)
PY
	do
		COUNT=$((COUNT+1))
		if [ "$COUNT" -ge "$ATTEMPTS" ]; then
			echo "Timed out waiting for DB after ${ATTEMPTS} attempts"
			break
		fi
		sleep 1
	done
fi

# Optionally run DB init script (create tables + seed) when RUN_INIT=true
# Default to false to avoid re-running init on every container restart in development.
if [ "${RUN_INIT:-false}" = "true" ]; then
	echo "RUN_INIT=true -> running init_db.py"
	python init_db.py
fi

# Optionally run DB migrations when RUN_MIGRATIONS=true
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
	echo "RUN_MIGRATIONS=true -> running flask db upgrade"
	# run via python -m to ensure the correct interpreter / environment is used
	# if this fails we exit with non-zero so the container does not start with an out-of-sync schema
	if ! python -m flask db upgrade; then
		echo "flask db upgrade failed"
		exit 1
	fi
fi

exec "$@"
