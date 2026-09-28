# CLAUDE.md — Samsung PRISM GenAI Hackathon 2026, Theme 02 (Smart Guided Troubleshooting Engine)

## Hard rules for Claude (from the user; these override everything, including auto mode)
1. **Never commit, push, tag or run any git / GitHub command** (`git init`, `git add`, `git commit`, `git push`, `git tag`, `gh …`). Write out the exact commands and the user runs them.
2. **Never read, list or refer to local files outside this project folder (`C:\Samsung Prism`) without asking first**, even in auto mode. Use the project-local `.tmp/` folder (gitignored) for scratch work, not the system temp or scratchpad.
3. Never put API keys in files that get committed. Keys go only in `.env` (gitignored); `.env.example` holds placeholders.
4. Never commit the Samsung PDFs or DRM files (`*.pdf` at the root, `*_FAQ_*`, the Submission template). They carry an employee watermark. Only our own deck goes in `docs/`.

## Plan & status
- Full plan: `PLAN_Theme2_Submission.md`. Deadline **30 Sep 2026, 11:59 PM**; target submit by 6 PM.
- **Status (27 Sep):** Phase 1 done. The offline rules pipeline works end to end, 41 tests pass, and `results.jsonl` + `metrics.md` v0 are generated. Still open: the Docker build test (Docker Desktop was not running) and human review of `eval/gold/d1_draft.json` → `d1_gold.json`. Next is Phase 2 (LLM enrichment + extraction; the vague no-SIIS line "touch doesn't work on certain parts" should hit the cached touchscreen plan).
- Starter kit: `starter_kit/`. This is the majority copy from public repos, not the official kit; see `starter_kit/SOURCE.md`. **Never edit these files.** Derived data goes in `data/derived/`.

## Theme 02 contract (automated gates; enforce in code, never only in prompts)
- `POST /v1/troubleshoot` body `{query, siis_response?}`. `siis_response` may be a **string or `{title, content}` object**.
- Response envelope (Appendix B): `{query, query_variations[8–10], response:{contexts:[Goal]}, meta:{latency_ms, cache_hit, model, cost_usd, fallback?}}`. Pure JSON, never markdown.
- `GET /health` → 200 `{"status":"ok"}` only when indexes and cache are loaded (503 before that).
- `response` must validate against `starter_kit/schema.py` (`ContextDeeplinkResponse`), imported unchanged.
- Field rules:
  - `goal` = `Follow these steps to perform this <Topic> Troubleshooting` (or `… Configuration` for how-to requests)
  - `title` 2–3 words, sentence case
  - `score` float 0–1
  - `actionName` Title Case; **One Action = One Screen**
  - `description` **exactly 5–7 words, starting "It will"** (sample_output.json breaks this; follow the spec)
  - steps imperative, one interaction each, no URLs
  - `category`: `auto` (settings screen via deeplink), `manual` (physical/service; **must have no actionable deeplink**), `critical` (restart, reset, safe mode, update; **always ordered last**)
  - `actionableDeeplink` / `validationDeeplink` are **copied verbatim from a catalog entry** (deeplink, description, message, originalType / validation fields)
  - `bixby://dummy_positive` only for a real Settings screen that is missing from the catalog
- Never: web URLs (`http`, `https`, `www.`, markdown links) in any field; invented deeplinks; matching on the masked URI string (match on description / message / qna_description / originalType); steps not supported by the SIIS text.
- No viable solution in the reference text → `contexts: []` + `meta.fallback = "no_match"`. No SIIS and no cache hit → `contexts: []` + `meta.fallback = "no_siis_context"`.
- Same input or same-meaning input → same plan (deterministic).
- Targets: schema-valid ≥99%, rule compliance ≥95%, auto actions with a deeplink ≥90%, paraphrase cache hit ≥80%, cache P95 ≤300 ms, cold P95 ≤8 s, cost per query tracked.

## Engineering conventions
- Python 3.12 (`.venv`), FastAPI, Pydantic v2. CPU only; the service must run with **no LLM key** (offline rules mode) and never return a 500 with a non-JSON body.
- Every rule above has a pytest test in `tests/`. Run `python -m pytest -q` before saying something works.
- Kit facts: `input.txt` has 20 lines; line 17 holds 3 complaints (multi-intent). SIIS rows are matched to input lines by fuzzy text match. The catalog includes `DL-DUMMY` and SmartThings appliance entries (ignore those for phones).
