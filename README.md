# Smart Guided Troubleshooting Engine
**Samsung PRISM GenAI Hackathon 2026 (3rd Edition) — Theme 02**

Turns a vague Galaxy device complaint ("screen flickers and goes blank") into a clean, ordered troubleshooting plan. Each step is grounded in the reference text, and each Settings step carries a one-tap deeplink copied exactly from the official catalog. Answers come back as pure JSON through a REST API.

> Status: **Phase 1 — walking skeleton (offline rules mode, no API key needed).** The LLM-based enrichment and extraction, the demo UI and the full evaluation arrive in later phases.

## Quickstart (Docker)
```bash
docker compose up --build
curl http://localhost:8000/health
curl -X POST http://localhost:8000/v1/troubleshoot -H "content-type: application/json" \
     -d '{"query": "My Galaxy S22 touch screen is laggy and inputs are delayed"}'
```
The image bakes in the embedding model and a cache pre-warmed from the official kit, so it needs no downloads or API keys at runtime. Open http://localhost:8000 for a test console, or http://localhost:8000/docs for the API docs.

## Quickstart (local, Python 3.12)
```bash
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/build_index.py && python scripts/warm_cache.py
uvicorn app.main:app --port 8000
```

## API
`POST /v1/troubleshoot`
```json
{ "query": "phone swipe gestures wrong direction after app install",
  "siis_response": "<optional reference text>  — or the kit's {\"title\": ..., \"content\": ...} object" }
```
Returns `{query, query_variations[8-10], response: {contexts: [Goal]}, meta: {latency_ms, cache_hit, model, cost_usd, fallback?}}`. `response` validates against the official `schema.py`.
- Reference text with no viable fix → `contexts: []`, `meta.fallback: "no_match"`
- No reference text and no cache hit → `contexts: []`, `meta.fallback: "no_siis_context"`
- Add `?debug=true` to get the decision trace (relevance scores, kept/dropped sections).

`GET /health` → `{"status": "ok"}` once the index, model and cache are loaded (503 before that).

## How it works
| Stage | What it does |
|---|---|
| 0. Query enrichment | Splits multi-complaint inputs, finds device, symptom, domain and trigger, builds the goal/title and 8–10 query variations in 5 registers |
| 1. Structure extraction | Parses the reference text into candidate actions. A Settings path plus its follow-up taps is one action (**One Action = One Screen**). Every step is a rewrite of a source sentence (nothing invented) |
| 2. Deeplink mapping & ordering | Settings Feature Graph built from the 578 catalog entries. Hybrid BM25 + dense search over descriptions only (never the masked URI), with action-aware (on/off/view/adjust) and depth-aware (exact screen, not parent menu) reranking. Order: settings → manual checks → service → critical (restart < safe mode < update < reset) |
| Contract gate | Programmatic checks for every rule (casing, "It will" 5–7 words, no URLs, verbatim catalog links, manual has no link, critical last) plus official schema validation |
| 3. Fast-path cache | Exact + semantic lookup over stored query variations, with a symptom guard. No LLM, $0 per hit |
| 4. REST API | FastAPI. Always JSON, including errors |

## Results
See [`metrics.md`](metrics.md) (Appendix-C template) and [`results.jsonl`](results.jsonl). Regenerate them with:
```bash
python scripts/gen_results.py      # results.jsonl, one line per input.txt line
python eval/run_eval.py            # metrics.md
python -m pytest -q                # contract + API tests
```

## Repository layout
`app/` engine · `starter_kit/Theme 2/` official kit (unchanged) · `data/derived/` generated index and cache · `scripts/` build/warm/results/labelling · `eval/` evaluation and gold labels · `tests/` · `ui/` · `Dockerfile`, `docker-compose.yml`

## Notes
- `starter_kit/Theme 2/` is the official Theme 2 kit (brand-neutral: `voiceassist://` deeplinks, TechCorp/Nexa device names). See `starter_kit/SOURCE.md`.
- `sample_output.json` has descriptions of 8 and 12 words. We follow the spec's rule of exactly 5–7 words starting with "It will".
