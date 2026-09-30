# FixFlow — Smart Guided Troubleshooting Engine
**Samsung PRISM GenAI Hackathon 2026 (3rd Edition) · Theme 02 · Team SRMIST_QueueQueueing**

FixFlow turns a vague device complaint ("screen flickers and goes blank") into a clean, ordered troubleshooting plan:
- Every step is **grounded in the reference article**, and the code rejects any step the article doesn't support.
- Every Settings step carries a **one-tap deeplink copied exactly from the official catalog**.
- Plans are ordered from least to most disruptive, with restarts and resets always last.

Answers are pure JSON from a REST API. Repeat and paraphrased complaints are answered from a pre-validated cache in milliseconds, at $0.

## Submission
| | |
|---|---|
| Theme | **02 — Smart Guided Troubleshooting Engine** |
| Team | **SRMIST_QueueQueueing** (SRM Institute of Science and Technology): Abhinav Kumar (RA2411003010993, ak8045@srmist.edu.in, primary member) · Abhishek Verma (RA2411003012011, av8372@srmist.edu.in) · Ayushi Paul (RA2411003010997, ap1547@srmist.edu.in) · Ketki Gonnade (RA2411003010739, kg0184@srmist.edu.in) |
| Presentation | [`docs/SRMIST_QueueQueueing.pptx`](docs/SRMIST_QueueQueueing.pptx) · [`docs/SRMIST_QueueQueueing.pdf`](docs/SRMIST_QueueQueueing.pdf) |
| Demo video (≤ 5 min) | VIDEO_LINK |
| Metrics / per-line output | [`metrics.md`](metrics.md) · [`results.jsonl`](results.jsonl) |
| Release tag | `PRISM_GENAI_HACKATHON_Y2026` |

## Quickstart (Docker, no API key needed)
```bash
docker compose up --build
curl http://localhost:8000/health
curl -X POST http://localhost:8000/v1/troubleshoot -H "content-type: application/json" \
     -d '{"query": "The touch doesn'"'"'t work on certain parts of the screen."}'
```
Open **http://localhost:8000** for the demo UI (phone view + engine view) or **/docs** for the API docs.

The image bakes in the embedding model and ships the pre-validated plan cache, so it needs no downloads at runtime. To enable the LLM cold path, copy `.env.example` to `.env` and set `LLM_API_KEY` (Google AI Studio / Gemini). Without a key, the engine runs its offline rules pipeline.

## Quickstart (local, Python 3.12)
```bash
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/build_index.py
uvicorn app.main:app --port 8000                    # Windows: .venv\Scripts\python -m uvicorn app.main:app --port 8000
```

## Using the demo UI (http://localhost:8000)
- **Left, phone view:** type or speak a complaint (or pick one of the 20 official complaints) and press **Find fix**.
  - The plan appears as cards, least disruptive first.
  - **Open** applies a Settings step (simulated), and **Verify** checks it with the step's validation deeplink.
  - Restart and reset steps ask for confirmation.
  - **Start guided fix** walks one step at a time ("Fixed?" / "Next step").
- **Right, engine view:** which path answered (cache, LLM or rules), latency, cost, deeplinks, contract gate, and the raw JSON.
- **New complaint, no article:** the API answers only from the pre-validated cache, as the contract requires. If nothing matches, the UI searches the knowledge base (the official kit's articles, via `/v1/kb/search`) and runs the full grounded pipeline on the best article.
  - A strong match (65% or more) is used automatically.
  - Otherwise the two closest articles are offered as buttons, and the UI never invents a plan.
- **Voice (🎤):** needs **Chrome or Edge**, internet (the browser's speech service) and microphone permission. Any problem (blocked mic, no microphone, service unreachable) is shown under the input box.
- **Demo links:**
  - `/?sample=18&verify=1`: touch lag, with Open → Verify done automatically
  - `/?sample=5`: an article that doesn't fit, so `no_match`
  - `/?sample=16`: three complaints in one line

### Try typing these complaints
| Complaint | What happens |
|---|---|
| `touch screen is laggy and slow to respond` | Cache hit: **Enable Touch Sensitivity** and **Open Navigation Bar Settings**, both with catalog deeplinks, then checks and restart/safe mode last |
| `touchscreen not working in some areas` | Cache hit: the same touchscreen plan from a differently worded complaint |
| `my display is completely dark and nothing shows` | Cache hit: check damage → charge → power on → contact support → force restart (critical, last) |
| `phone screen is black but it still rings` | Cache hit: black-screen plan (data access via mouse/monitor, force restart) |
| `screen got cracked after I dropped my phone` | Cache hit: repair and care-plan options, no invented settings steps |
| `gmail app shows a blank screen when I open an email` | Cache hit: Wi-Fi and app-storage settings (deeplinks), then Safe mode |
| `can't transfer data to my new tablet, the qr code won't scan` | Cache hit: open the Data Transfer app (steps from the transfer article) |
| `the screen doesn't rotate when I turn my phone sideways` | New complaint: the knowledge base finds the rotation article (90% match) → orientation settings, test app rotation, support |
| `how do I mirror my phone screen to my TV` | New complaint: matched to the screen-mirroring article (74%) → Smart View steps |
| `my battery drains really fast` | Honest limit: the kit has no battery article, so the UI shows the closest articles instead of inventing a fix |

With an LLM key in `.env`, new complaints go through Gemini (the rules path answers if it is unavailable), so the wording of the steps can differ slightly from the table.

**Testing tip:** every new plan is written into `data/derived/cache.sqlite`. To keep the shipped cache clean while testing, set `CACHE_WRITE=0` in `.env`, or restore that file before committing.

## API (Theme 02 contract)
`POST /v1/troubleshoot`
```json
{ "query": "phone swipe gestures wrong direction after app install",
  "siis_response": "<optional reference text>  — or the kit's {\"title\": ..., \"content\": ...} object" }
```
Returns `{query, query_variations[8-10], response: {contexts: [Goal]}, meta: {latency_ms, cache_hit, model, cost_usd, fallback?}}`. The `response` validates against the official `schema.py`, imported unchanged.
- The reference text has no viable fix → `contexts: []`, `meta.fallback: "no_match"` (nothing is invented).
- No reference text and no cache hit → `contexts: []`, `meta.fallback: "no_siis_context"`.
- Errors are still JSON envelopes (`invalid_request`, `internal_error`).
- `?debug=true` adds a decision trace (cache similarity, LLM usage, dropped unsupported steps, relevance scores).

`GET /health` → `{"status": "ok"}` once the index, model and cache are loaded (503 before that).

Demo helpers (outside the Theme 02 contract, used by the UI): `GET /v1/samples` (the 20 official complaints with their articles) and `GET /v1/kb/search?q=…` (best-matching knowledge-base articles for a complaint).

Windows PowerShell example:
```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/v1/troubleshoot -ContentType "application/json" -Body '{"query": "touch screen is laggy and slow to respond"}' | ConvertTo-Json -Depth 10
```

## How it works
```
complaint (+ reference article)
 → [3] fast-path cache: L1 exact/semantic on the query, L2 on the normalised complaint; symptom guard; $0, ~30 ms
 → [0] enrichment: normalised technical query + 8–10 variations (LLM, rules fallback), multi-complaint split
 → [1] grounded extraction: LLM reads the article as numbered sentences; every step must cite them,
       and code drops steps whose content is not in the cited sentences (rules parser if no LLM)
 → [2] deeplink mapping: Settings Feature Graph over 578 entries, hybrid BM25 + dense search on descriptions
       (never the masked URI), action-aware (on/off/view/adjust) and depth-aware (exact screen, not parent menu)
 → contract gate: casing, "It will" 5–7 words, no URLs, verbatim catalog links, manual has no link,
       critical last, official schema validation
 → [4] JSON envelope; plan stored in the cache (trust tiers: auto / provisional)
```
- **LLM:** Gemini (auto-picks the newest Flash-Lite, with fallback across models, retry with backoff and a time budget). If every model is unavailable, the offline rules path answers, so requests never fail.
- **Deterministic:** temperature 0 with a fixed seed; the cache returns the identical plan for identical or same-meaning complaints.

## Results
Full report: [`metrics.md`](metrics.md) (Appendix-C template: gates, accuracy, latency, cost, ablation). Per-line output: [`results.jsonl`](results.jsonl).
```bash
python scripts/warm_cache.py --llm-budget 60   # compile the official lines into the cache (LLM, batch)
python scripts/gen_results.py                  # results.jsonl, one line per input.txt line
python eval/run_eval.py                        # metrics.md   (--offline for rules-only)
python eval/ablation.py                        # 3-way deeplink-mapping ablation
python -m pytest -q                            # contract, API and LLM-path tests (hermetic)
```

## Repository layout
`app/` engine (`kb.py` = knowledge-base article search for the UI) · `ui/` demo · `starter_kit/Theme 2/` official kit (unchanged) · `data/derived/` index + pre-validated cache · `scripts/` build / warm / results / labelling · `eval/` datasets, gold labels, harness, ablation · `tests/` (48) · `docs/` deck (PPTX + PDF, built on the official template by `docs/deck_src/`), pitch script (`docs/PITCH.md`), UI screenshot · `Dockerfile`, `docker-compose.yml`

## Notes
- `starter_kit/Theme 2/` is the official Theme 2 kit (brand-neutral: `voiceassist://` deeplinks, TechCorp/Nexa names). See `starter_kit/SOURCE.md`.
- `sample_output.json` has descriptions of 8 and 12 words. We follow the spec's rule of exactly 5–7 words starting with "It will".
- The contract says critical actions come last, so service-centre escalation is listed before restarts and resets.
