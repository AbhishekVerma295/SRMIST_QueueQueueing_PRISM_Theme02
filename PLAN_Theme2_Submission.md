# Samsung PRISM GenAI Hackathon 2026 (3rd Ed.) — Theme 02 Winning Plan

## Status — 28 Sep 2026 (read this first)
| Item | State |
|---|---|
| Phase 0 | Registration/deadline: user-confirmed 30 Sep. **Official kit received and in use.** FAQ v4 + PPT template still DRM-locked |
| Phase 1 | **Done** on the official kit: API, validators, catalog resolver, rules extraction, cache, 42 tests, results.jsonl, metrics.md v0, gold labels D1 |
| Metrics (20 official lines, offline mode) | Gates 100% (schema, rules, 0 URL leaks, catalog validity, auto links) · deeplink relevance 2.00/2 · deeplink precision 100% · abstention 95% · cache P95 25 ms · cold P95 ~0.25 s · $0 |
| Open from Phase 1 | Docker build test (Docker Desktop must be running) · human spot-check of `eval/gold/d1_gold.json` |
| Needed from user | Gemini API key (Google AI Studio) in `.env` → unblocks Phase 2 · GitHub repo created (user runs all git commands) |
| **Next** | Phase 2: LLM enrichment + grounded extraction (fixes coarse offline relevance: row_16 abstains; rows 3/11/17 keep an irrelevant Screen-lock action on a dummy link), L2 canonical cache, paraphrase set D3, held-out D2, step-accuracy judge |

## 0. Context
- **Theme 02 – Smart Guided Troubleshooting Engine.** Goal: be in the **Top 15 (9 Oct)** → final demo 15 Oct → win (internship/PPO, worklet, ₹1.5L pool).
- **No ideation round this year.** The "first submission" IS the full build: working repo + Docker + ≤5-min video + PPT, via Google Form. User confirms deadline **30 Sep** (the deck said 25 Sep) and says the team is registered. Get both confirmed in writing (Phase 0).
- Nobody can guarantee 100%: Top-15 covers all 5 themes, and ≥20 Theme-02 repos are already public. The plan removes every disqualification risk and targets every rubric line.
- Team: effectively **2 people + Claude Code each**, long hours OK. Tasks are listed **in dependency order in two parallel lanes**; the user assigns them.
- Sources read: event deck PDF, Theme 2 spec PDF (contract, schema.py, metrics template), public competitor repos (used to learn the starter-kit format and the competitive bar). Nothing public was found about the Teams call.
- **Found on this PC (Downloads, saved 24 Sep 10:25 PM, right after the Teams call):** `Samsung_PRISM_GenAI_Hackathon_3_FAQ_v4.docx` and the official template `CollegeName_TeamName_Submission.pptx`. **Both are encrypted with Samsung's NASCA DRM** and won't open on a normal PC. Getting readable (PDF) copies is now a Phase 0 task. The FAQ may confirm or change rules (deadline, kit, API keys, how evaluation runs), so re-check this plan against it the moment it's readable.

## 1. Rules that decide selection (event deck)
| Item | Requirement |
|---|---|
| Rubric | Working prototype 30% · Technical depth & feasibility 25% · Innovation 20% · Relevance to theme 15% · Presentation & docs 10% |
| Jury (final) | Does it work? Is the approach sound? Would a real user want it? Can it become a worklet? |
| Repo | Public or shared GitHub; README with reproducible setup, **Dockerfile**, requirements |
| Tag | **`PRISM_GENAI_HACKATHON_Y2026`** on the final commit — only the tagged commit is judged; PPT, video link and docs must be **inside it** |
| Video | ≤ 5 min, YouTube/Drive link |
| PPT/PDF | File named `CollegeName_TeamName`, following the `CollegeName_TeamName_Submission_ppt` template. Contains: Theme ID, title, team, problem in own words, solution + architecture diagram, tech stack, innovation, results, limitations |
| Other | One submission per registered team via Google Form. Breaking any submission rule = **direct disqualification** |

## 2. Theme 02 contract (what automated gates will check)
- **API:** `POST /v1/troubleshoot` `{query, siis_response?}` → `{query, query_variations[8–10], response:{contexts:[Goal]}, meta:{latency_ms, cache_hit, model, cost_usd, fallback?}}`; `GET /health` → 200 `{"status":"ok"}` only when cache, model and indexes are ready. Pure JSON, no markdown.
- **Fields:** goal = `Follow these steps to perform this <Topic> Troubleshooting|Configuration`; title 2–3 words, sentence case; score 0–1; actionName Title Case, **One Action = One Screen**; description **5–7 words starting "It will"**; steps imperative, one interaction each, no URLs; **manual has no deeplink; critical always last**; actionable + validation deeplinks copied **verbatim** from the catalog. `bixby://dummy_positive` only for a real Settings screen that isn't in the catalog.
- **Non-negotiables:** zero URL leaks · match on description/message/qna_description, never the masked URI · no invented steps → `contexts: []` + `fallback: "no_match"` (no SIIS and no cache hit → `"no_siis_context"`) · same output for identical or same-meaning inputs.
- **Targets:** schema-valid ≥99% · rule compliance ≥95% · auto actions with a deeplink ≥90% · paraphrase cache hit ≥80% · cache P95 ≤300 ms · cold P95 ≤8 s · cost per query tracked.
- **Required artifacts:** `results.jsonl` (one Appendix-B line per input query) and `metrics.md` (Appendix C template, including the 3-way ablation: full-LLM mapping / hybrid BM25+dense / pure rules).

## 3. Starter kit (OFFICIAL kit received 28 Sep, in `starter_kit/Theme 2/`)
- **Official kit is brand-neutral:** `voiceassist://masked/...` deeplinks, placeholder `voiceassist://dummy_positive`, TechCorp/Nexa device names, Data Transfer (= Smart Switch), Customer Support. Same structure and DL ids as the public copy. The DL-DUMMY entry asks for a 5–7 word description/message naming the concrete screen.
- (Superseded: 26 Sep majority copy from public repos, now in `starter_kit/_unofficial_public_copy/`.) `input.txt` has **20 lines**, almost all **Display**; line 17 packs **3 complaints** (cracked fold / dead touch zones / can hardly see) and is a built-in **multi-intent** test. `siis_responses.json` has 20 rows `{id, original_query, siis_response:{title, content}}`, one per line. Match lines to SIIS rows with fuzzy matching, since the query text differs slightly. The catalog also has `DL-DUMMY` (dummy_positive), 3 "Diagnose battery/performance/overheating" entries and some SmartThings appliance noise. About **6 rows have a mismatched SIIS** (these test abstention). Six rows share the "Blank or black display" text.
- `deeplinks.json` 578 entries: `id, deeplink (…/act/…), description, message, originalType (onClickURL|onURL|offURL|updateURL), control_type, qna_description, validation{deeplink (…/val/…), key, resultType, condition, value}`. On/off pairs share one validation key.
- `sample_output.json` includes a verbatim `validationDeeplink`, but its descriptions are 8 and 12 words, which **breaks the spec's 5–7 rule**. We follow the spec and note it in the README.
- **Design consequences:** accept `siis_response` as a **string or `{title, content}`** (otherwise the judges' harness may get 422 errors). Hidden tests likely cover **Battery/Camera/Performance** too, so we generalise instead of fitting the 20 rows. The shipped cache holds only plans built from official kit text; synthetic data stays eval-only.

## 4. Competitive bar → our edge
Table stakes that everyone already has (OneClick, GASTE, FixRoute, TapFix, aush5895/Prism, Aadi546, MonikashreeDev…): FastAPI + Pydantic + BM25/TF-IDF/dense + semantic cache + Docker. Their claims (100% schema, 0 leaks, P95 < 100 ms, 80–100% paraphrase hits) are **all measured on the 20 given rows**. Some also have closed-loop validation, a Next.js/PWA UI, OCR input or Hinglish input.
**We win on:** (1) **proof of generalisation**: a held-out 4-domain set, unseen paraphrases and adversarial tests, reported honestly; (2) **exact-screen precision** from a Settings Feature Graph with action-aware and depth-aware matching; (3) a **trust-tiered cache** (no cache poisoning) plus a **reusable Action Library with a 10k-scenario benchmark**, which is the spec's production target; (4) a **guided Tap→Verify phone demo** with voice input; (5) **spec-native packaging**: the same stage names and the exact metrics.md template.
Rules for us: never copy competitor code; keep the repo **private until submission day**.

## 5. Architecture (working name: FixPilot / TapRight / SettleIt, team picks one)
```
POST /v1/troubleshoot {query, siis_response?: str|{title,content}}
 ├ G0 Input guard: size caps, strip URLs and injected instructions from siis, normalise text
 ├ [3a] L1 fast path (no LLM, target P95 < 50 ms): exact hash → bge-small embedding vs stored query_variations
 │      + slot guard (domain/symptom lexicon) + same-SIIS check + trust tier ≥ auto → HIT: return plan, cost 0
 ├ [0] Query Enrichment (LLM call 1, JSON-schema, temp 0): canonical technical query, slots (domain, symptoms,
 │      trigger, device, feature), request type (fault → Troubleshooting | how-to → Configuration), intents[] (multi-intent),
 │      8–10 variations in 5 registers + a programmatic typo variant, deduped
 │      └ [3b] L2 cache check on the canonical query; no siis and no hit → [] + "no_siis_context"
 ├ [1] Grounded Extraction (LLM call 2): SIIS split into numbered sentences S1..Sn → relevance verdict per intent
 │      → actions[{screen, kind: settings|toggle|physical|disruptive, steps[{text, cites:[Sk]}]}]
 │      → grounding verifier drops unsupported steps; nothing relevant → [] + "no_match"
 ├ [2] Deeplink Mapping & Sequencing (deterministic): Feature Graph built offline from the 578 entries (on/off twins,
 │      operations, screen paths, alias lexicon, e.g. "floating circle" → Assistant menu) → BM25 + dense → RRF
 │      → action-aware rerank (enable→onURL, disable→offURL, open/check→onClickURL, adjust→updateURL)
 │      → depth-aware rerank (exact screen > parent menu) → confidence + margin gate
 │      → auto (verbatim links) | dummy_positive | manual (no link) | critical → 1-action-1-screen merge/split
 │      → disruption ordering (toggle < app-level < physical check < escalation; critical always last)
 ├ Contract compiler: templates, casing, "It will" 5–7 words, step splitting, URL/markdown scrubber, catalog membership,
 │      official schema.py strict validation, calibrated score. Repair order: deterministic → 1 batched LLM repair → template
 ├ [3c] Cache write with trust tier (validated / auto / provisional) + Action Library upsert
 └ [4] Envelope exactly as Appendix B; ?debug=true adds a trace (citations, candidates, stage timings) for the UI
```
- **Determinism:** plan = f(canonical issue, SIIS hash); temp 0 + seed; cache-first; stable tie-breaks.
- **Judge has no key / no internet:** an offline mode replaces LLM calls 1–2 with a rules-based SIIS parser and template-based variations. The embedding model is baked into the image and the cache ships pre-warmed. The API never 500s; errors still return a JSON envelope.
- **Stack:** Python 3.11, FastAPI, Pydantic v2 (official `schema.py` imported unchanged), a provider-agnostic LLM adapter (default: Gemini Flash-class via a free AI Studio key; OpenAI/Groq/Claude also supported; check current model IDs and prices in provider docs when building), fastembed `bge-small-en-v1.5` (ONNX, CPU), rank-bm25, SQLite + NumPy (HNSW for the 10k benchmark), pytest, Docker + compose. Static HTML/JS demo at `/demo` with the browser Web Speech API for voice.

## 6. Innovation pillars (each needs a number in metrics.md and a slide)
| Pillar | Evidence |
|---|---|
| Citation-grounded extraction + auto-abstention | grounding rate, correct no_match on mismatched SIIS |
| Feature Graph, action-aware + depth-aware deeplinks | deeplink relevance 0–2, parent-menu error rate, ablation delta |
| Trust-tiered two-level semantic cache | hit rate **and false-hit rate** on unseen paraphrases, P50/P95 |
| Reusable Action Library for 10k+ scenarios | reuse %, cost-per-new-scenario curve, P95 at 10k keys |
| Guided Tap→Verify + multimodal intake (voice; screenshot is P2) | live demo, closed-loop coverage % |
PPT framing for the hackathon headline ("multimodal, agentic"): a verifier-driven agent loop (plan → extract → map → validate → repair or abstain) + voice intake.

## 7. Evaluation → `metrics.md`
D1 official 20 input lines (22 complaints incl. the multi-intent line) with hand-labelled gold (relevant?, actions, deeplink IDs, category, order) · D2 held-out ~40 scenarios (10 each for Battery/Display/Camera/Performance; reference text is our own writing) · D3 ~150 unseen paraphrases (typos, keyword-only, Hinglish) + ~50 hard negatives · D4 adversarial (URL/prompt injection in siis, empty/huge input, irrelevant SIIS, multi-intent).
Report: all Appendix-C rows · step accuracy 0–3 and deeplink relevance 0–2 (LLM judge checked against humans on D1) · P50/P95 with N ≥ 30 per path · cost/query · hit and false-hit rate · determinism (10 runs → same hash) · 3-way ablation · limitations.

## 8. Repo layout
`app/` (api, pipeline/{enrich,extract,map,order,compile}, retrieval/, cache/, llm/, validators/) · `data/` (official kit unchanged + derived feature_graph.json, aliases.json, cache.sqlite) · `eval/` · `scripts/` (build_index, warm_cache, gen_results, compile_kb) · `ui/` · `tests/` · `docs/` (PPT/PDF, architecture diagram, spec PDFs) · `results.jsonl` · `metrics.md` · `README.md` · `CLAUDE.md` (contract rules so every Claude Code session enforces them) · `Dockerfile` · `docker-compose.yml` · `.env.example` (never commit keys) · pinned `requirements.txt` · `Makefile`.

## 9. Ordered task list (Lane E = engine, Lane Q = data/eval/UI/docs; lanes run in parallel)
**Phase 0 — Unblock (24 Sep, tonight)**
1. Confirm registration + 30 Sep in writing. Check: the registrant's inbox for the Google Forms receipt; whether you received the final-submission form link (it only goes to registered teams); the reg. form showing "You've already responded" when opened with the same Google account; your campus PRISM coordinator; an email to prism@samsung.com (team name, college, members). In the same email, ask for the kit **and for DRM-free PDF copies of FAQ v4 and the submission template** (the downloaded .docx/.pptx are NASCA-DRM-locked). Also ask in the Teams channel or college group where they were shared; other teams are probably stuck on the same thing.
2. Get the kit: open the **original .pptx** (not the PDF) and double-click the embedded "Smartguided word Guide" on the Theme 2 slide; also check PRISM emails and the coordinator. Stopgap only: the same files are visible in public participant repos. Verify 578 deeplinks / 20 SIIS rows / schema.py matches Appendix A, and swap in the official copy when it arrives.
3. Get an LLM key; create the private repo with the §8 skeleton; commit the kit, PDFs, CLAUDE.md and this plan.

**Phase 1 — Walking skeleton, always shippable (25 Sep)**
- E: FastAPI contract (siis str|object, /health readiness, JSON errors) → strict validators + tests → Feature Graph + hybrid index → rules-based parser → mapping → compiler → Dockerfile (model baked) + `make results`. **Checkpoint: Docker returns schema-valid JSON for all 20 input lines.**
- Q: labelling helper (top-10 candidates per step) → gold labels for D1 → eval harness v0 (gates + deeplink relevance).

**Phase 2 — Intelligence (26 Sep)**
- E: enrichment prompt + variations → grounded extraction + verifier + no_match → alias lexicon + action/depth rerank + gates + dummy_positive policy → ordering + repair loop → L1/L2 cache, trust tiers, SQLite, pre-warm.
- Q: D3 paraphrases + negatives → D2 held-out scenarios + gold → step-accuracy judge + human check.

**Phase 3 — Measure & generalise (27 Sep)**
- E: at least 2 error-analysis/fix loops on D2/D3 (not just D1) → multi-intent contexts → D4 adversarial fixes → determinism + concurrency tests.
- Q: 3-way ablation → latency bench (N ≥ 30) + cost accounting → metrics.md v1.

**Phase 4 — Differentiators (28 Sep, feature freeze 8 PM)**
- E: Action Library + 10k/100k scale benchmark → score calibration → clean-machine Docker test with and without a key (ARM if possible).
- Q: demo UI (phone view with Open/Verify and guided "Fixed? / Next"; trace view with stages, timings, cache, cost, citations) + Tap→Verify simulator + voice input. P2 if time: screenshot intake, Hinglish demo, streaming.

**Phase 5 — Story (29 Sep)**
- Final eval run **from the Docker image** → metrics.md + results.jsonl · README (3-command quickstart, curl examples, design decisions, results, limitations, video link) · architecture diagram · PPT (~12 slides: title/team → problem → solution → architecture → extraction → deeplinks → cache → innovations → results + ablation → demo shots → limitations + worklet roadmap → links) · video (≤ 4:45: hook 20 s, architecture 30 s, 6-scenario live demo ~2:20, metrics 55 s, innovation + roadmap 30 s, close) · the second member reproduces everything from a fresh clone using only the README.

**Phase 6 — Ship (30 Sep, submit by 6 PM)**
- §10 checklist → commit → tag + GitHub Release → make repo public → incognito check → submit form → save the confirmation.
**Cut line if behind:** Phase 4 P2 items first, then the scale benchmark, then calibration. Never cut Phase 1–3, the README, the video or the checklist.

## 10. Submission checklist (disqualification-proof)
Team name `CollegeName_TeamName` · repo public/shared and opens in incognito · README gets a stranger running it in 3 commands · `docker compose up` works on a clean machine · tag spelled exactly `PRISM_GENAI_HACKATHON_Y2026` on the final commit (verify with `git ls-remote --tags`), never moved afterwards · PPT/PDF correctly named, following the template, **inside the tagged commit** · video ≤ 5:00, unlisted/anyone-with-link, linked in README + PPT + form · results.jsonl + metrics.md present · form submitted hours before 11:59 PM.

## 11. Risks → mitigations
Kit/template not obtained → Phase 0 tasks 1–2 today · FAQ v4 unreadable (DRM) → request a PDF; until then follow the deck + spec, then diff this plan against the FAQ · template unreadable → build the deck with every required section and the correct file name, then move the content into the template once it opens · judge has no key → offline mode + pre-warmed cache · siis type mismatch → accept both · overfitting → held-out set · sample-vs-spec conflict → follow the spec, document it · false cache hits between similar display issues → slot guards + calibrated threshold, report false hits · LLM non-determinism → canonical-issue keying · "critical last" vs service-centre logic → JSON follows the contract, UI shows escalation last · scope creep → cut line + freeze · Docker/tag/link failure → §10 + clean-room repro.

## 12. Verification (definition of done)
Fresh clone → `docker compose up` → `/health` 200 → `make results` writes 20 schema-valid lines → `pytest` green (schema, rules, leak, catalog, ordering, determinism, siis str/object, offline mode) → `make eval` regenerates metrics.md → demo walkthrough of 6 scenarios (cold, paraphrase hit, multi-intent, no_match, no-SIIS, Tap→Verify) → incognito check of repo, tag, video, PPT.
