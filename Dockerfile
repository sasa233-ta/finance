FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /

COPY requirements.txt /
# Install runtime system packages required by some Python packages (e.g. libgomp for OpenMP)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . /

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["/entrypoint.sh"]
# Allow runtime configuration of gunicorn workers and timeout via environment variables.
# GUNICORN_WORKERS: number of worker processes (default 3)
# GUNICORN_TIMEOUT: worker timeout in seconds (default 120)
# Use sh -c so environment variables like $PORT are expanded at runtime.
CMD ["sh", "-c", "gunicorn run:app --bind 0.0.0.0:${PORT:-5000} --workers ${GUNICORN_WORKERS:-3} --timeout ${GUNICORN_TIMEOUT:-120}"]
