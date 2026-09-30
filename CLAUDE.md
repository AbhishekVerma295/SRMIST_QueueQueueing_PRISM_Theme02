# CLAUDE.md — Samsung PRISM GenAI Hackathon 2026, Theme 02 (Smart Guided Troubleshooting Engine)

## Hard rules for Claude (from the user; these override everything, including auto mode)
1. **Never commit, push, tag or run any git / GitHub command** (`git init`, `git add`, `git commit`, `git push`, `git tag`, `gh …`). Write out the exact commands and the user runs them.
2. **Never read, list or refer to local files outside this project folder (`C:\Samsung Prism`) without asking first**, even in auto mode. Use the project-local `.tmp/` folder (gitignored) for scratch work, not the system temp or scratchpad.
3. Never put API keys in files that get committed. Keys go only in `.env` (gitignored); `.env.example` holds placeholders.
4. Never commit the Samsung PDFs or DRM files (`*.pdf` at the root, `*_FAQ_*`, the Submission template). They carry an employee watermark. Only our own deck goes in `docs/`.

## Plan & status
- Team: **SRMIST_QueueQueueing**. GitHub repo: `SRMIST_QueueQueueing_PRISM_Theme02`. PPT/PDF file name: `SRMIST_QueueQueueing`. Release tag: `PRISM_GENAI_HACKATHON_Y2026`.
- Full plan: `PLAN_Theme2_Submission.md`. Deadline **30 Sep 2026, 11:59 PM**; target submit by 6 PM.
- **Status (28 Sep, evening):** Phase 1 done on the official kit. Phase 2 code done: LLM adapter (`app/llm.py`, Gemini default), LLM enrichment + grounded extraction with citation check in code (`app/llm_stages.py`), L2 cache on the normalised complaint, symptom-aware cache thresholds, paraphrase sets D3 (tuning) + D3b (held-out, never tune on it). 47 tests pass (LLM path tested with a fake LLM). Offline metrics: gates 100%, deeplink relevance 2.00, precision 100%, abstention 95%, held-out paraphrase hit 83.3% / correct plan 79.2%, 1 false hit of 10 ("flashlight won't turn on"). Gold labels are Claude-annotated (human spot-check pending).
- **28 Sep night:** Docker image builds and serves (health 3 s). Live Gemini works but is heavily overloaded (503) and Flash free quota is spent (429). The adapter has a model fallback chain, backoff, dead-model skipping and an 8 s online budget, and the batch compile (`scripts/warm_cache.py --resume --llm-budget 90`) builds the pre-validated cache (commit `data/derived/cache.sqlite`). D2 (12 scenarios, 4 domains) written and used for one round of error analysis (now a dev set). Step-accuracy proxy in `eval/run_eval.py`; 3-way ablation `eval/ablation.py` (hybrid rel 1.76 / precision 100% vs rules 1.29 / 57.9%; the LLM baseline is pending API availability). Demo UI `ui/index.html` (phone view, Tap→Verify via validation links, guided mode, voice, engine view) served at `/` with `/v1/samples`.
- **28 Sep late:** Shipped cache = first LLM compile (12/20 lines by gemini-3.1-flash-lite, rest rules). A second compile with a tightened prompt scored lower under the same outage and was not shipped; the prompt change stays in code. `metrics.md` (LLM mode) and `metrics_offline.md` are generated. Gates are 100% on D1 and D2. Paraphrase metric now reports strict (same article) and lenient (same symptom) accuracy. The Docker image contains the shipped cache. `docs/PITCH.md` has the deck content and video script.
- **30 Sep 17:50:** Deck done: `docs/SRMIST_QueueQueueing.pptx` + `.pdf` (13 slides, validated, exported by PowerPoint; generator `docs/deck_src/build_deck.js`, run with `NODE_PATH=.tmp/deckgen/node_modules`; set `VIDEO_URL` to add the link to the closing slide). UI screenshot `docs/img/ui_demo.png`. UI supports `?sample=N&verify=1` for demos. README has a Submission table with a `VIDEO_LINK` placeholder that MUST be replaced before tagging. Product name: FixFlow. Team: Abhinav Kumar (primary, RA2411003010993), Abhishek Verma (RA2411003012011), Ayushi Paul (RA2411003010997), Ketki Gonnade (RA2411003010739).
- **30 Sep ~18:30:** The deck was rebuilt on the OFFICIAL template (`CollegeName_TeamName_Submission.pptx`, copied to `.tmp/template/template.pptx`, never committed) with `docs/deck_src/build_template_deck.py` (icons: `docs/deck_src/make_icons.js`; team/emails/video in `docs/deck_src/team.json`). 12 template sections filled; PDF exported via PowerPoint COM. `docs/PITCH.md` is split into 4 presenters (Abhinav 1–3, Abhishek 4–6, Ayushi 7–9, Ketki 10–12), and speaker notes name the presenter. Member emails are still missing (title slide).
- **Next:** emails → team.json → rebuild the deck and PDF · the user records the video → `video` in team.json + replace `VIDEO_LINK` in README → final commit → tag → push the tag → make public → submit the form before 11:59 PM.
- Starter kit: **official** kit in `starter_kit/Theme 2/` (see `starter_kit/SOURCE.md`). **Never edit these files.** Derived data goes in `data/derived/`. `starter_kit/_unofficial_public_copy/` is superseded and gitignored.

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
  - `voiceassist://dummy_positive` (read from the catalog's `DL-DUMMY` entry, never hardcoded) only for a real Settings screen missing from the catalog; its description and message are 5–7 words naming the concrete screen
- Never: web URLs (`http`, `https`, `www.`, markdown links) in any field; invented deeplinks; matching on the masked URI string (match on description / message / qna_description / originalType); steps not supported by the SIIS text.
- No viable solution in the reference text → `contexts: []` + `meta.fallback = "no_match"`. No SIIS and no cache hit → `contexts: []` + `meta.fallback = "no_siis_context"`.
- Same input or same-meaning input → same plan (deterministic).
- Targets: schema-valid ≥99%, rule compliance ≥95%, auto actions with a deeplink ≥90%, paraphrase cache hit ≥80%, cache P95 ≤300 ms, cold P95 ≤8 s, cost per query tracked.

## Engineering conventions
- Python 3.12 (`.venv`), FastAPI, Pydantic v2. CPU only; the service must run with **no LLM key** (offline rules mode) and never return a 500 with a non-JSON body.
- Every rule above has a pytest test in `tests/`. Run `python -m pytest -q` before saying something works.
- Kit facts: brand-neutral names (TechCorp, Nexa X1, Data Transfer, VoiceAssist, Customer Support). Never inject Samsung/Galaxy/Bixby wording into outputs (a test checks this). `input.txt` has 20 lines; line 17 holds 3 complaints (multi-intent). SIIS rows are matched to input lines by fuzzy text match. The catalog includes `DL-DUMMY` and SmartThings appliance entries (ignore those for phones).
