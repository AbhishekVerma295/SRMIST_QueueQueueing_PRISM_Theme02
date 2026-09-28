# Smart Guided Troubleshooting Engine — CPU only, runs with or without an LLM key.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODEL_CACHE=/app/models_cache \
    HF_HUB_DISABLE_TELEMETRY=1 \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY starter_kit ./starter_kit
COPY data ./data
COPY tests ./tests
COPY ui ./ui

# Bake the embedding model + catalog index into the image (no downloads at runtime),
# then pre-warm the cache from the official kit so the fast path works out of the box.
RUN python scripts/build_index.py && python scripts/warm_cache.py

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
  CMD python -c "import urllib.request,os,sys; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health').status==200 else 1)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
