FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RELIEFRELAY_DATABASE=/data/reliefrelay.db

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 reliefrelay \
    && mkdir -p /data /app/.local/whisper /app/models/whisper \
    && chown -R reliefrelay:reliefrelay /data /app

USER reliefrelay
EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"

CMD ["uvicorn", "reliefrelay.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
