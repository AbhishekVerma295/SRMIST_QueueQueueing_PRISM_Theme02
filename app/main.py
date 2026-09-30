"""REST API (Stage 4): POST /v1/troubleshoot, GET /health.

Always answers with JSON. Bad input -> 400/422 with the normal envelope and meta.fallback="invalid_request";
unexpected errors -> 500 with meta.fallback="internal_error". /health is 503 until the catalog index,
embedding model and cache are loaded.
"""
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from . import catalog, embed, pipeline

log = logging.getLogger("troubleshoot")
STATE = {"ready": False, "started": None}
UI_DIR = Path(__file__).resolve().parents[1] / "ui"


def _error_envelope(query: str, fallback: str, t0: float) -> dict:
    return {"query": query, "query_variations": [], "response": {"contexts": []},
            "meta": {"latency_ms": int((time.perf_counter() - t0) * 1000), "cache_hit": False,
                     "model": pipeline.MODEL_NAME, "cost_usd": 0.0, "fallback": fallback}}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    t = time.perf_counter()
    embed.warmup()
    catalog.get()
    pipeline.get_cache()
    STATE.update(ready=True, started=round(time.perf_counter() - t, 2))
    log.info("ready in %ss", STATE["started"])
    yield


app = FastAPI(title="Smart Guided Troubleshooting Engine", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    if not STATE["ready"]:
        return JSONResponse({"status": "starting"}, status_code=503)
    return {"status": "ok"}


@app.post("/v1/troubleshoot")
async def troubleshoot(request: Request):
    t0 = time.perf_counter()
    try:
        body = json.loads(await request.body() or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(_error_envelope("", "invalid_request", t0), status_code=400)
    if not isinstance(body, dict) or not isinstance(body.get("query"), str) or not body["query"].strip():
        q = body.get("query") if isinstance(body, dict) and isinstance(body.get("query"), str) else ""
        return JSONResponse(_error_envelope(q, "invalid_request", t0), status_code=422)
    siis = body.get("siis_response")
    if siis is not None and not isinstance(siis, (str, dict)):
        siis = json.dumps(siis)
    debug = request.query_params.get("debug", "").lower() in ("1", "true", "yes")
    try:
        return JSONResponse(pipeline.troubleshoot(body["query"], siis, debug=debug))
    except Exception:  # never leak a stack trace or a non-JSON body
        log.exception("pipeline failure")
        return JSONResponse(_error_envelope(body["query"], "internal_error", t0), status_code=500)


@app.get("/v1/kb/search")
def kb_search(q: str = ""):
    """Demo helper (not part of the Theme 02 contract): best-matching knowledge-base articles for a complaint."""
    from . import kb
    if not q.strip():
        return {"results": []}
    return {"results": kb.search(q[:2000])}


@app.get("/v1/samples")
def samples():
    """Demo helper (not part of the Theme 02 contract): official input lines with their reference texts."""
    from . import kit
    out = []
    for q in kit.input_queries():
        row = kit.match_siis(q)
        out.append({"id": (row or {}).get("id"), "query": q, "siis_response": (row or {}).get("siis_response")})
    return {"samples": out}


@app.get("/")
def root():
    index = UI_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"service": "Smart Guided Troubleshooting Engine", "endpoints": ["POST /v1/troubleshoot", "GET /health", "GET /docs"]}
