# FixFlow — pitch and demo-video script (4 presenters)
Team **SRMIST_QueueQueueing** · Theme 02 · Smart Guided Troubleshooting Engine
Deck: `docs/SRMIST_QueueQueueing.pptx` / `.pdf`, built on the official `CollegeName_TeamName_Submission` template (12 sections). Each slide's speaker notes name its presenter.

**Video target: 4:40 in total (hard limit 5:00), about 70 seconds per person.** Record one continuous screen capture, passing the "mic" from person to person, or record four clips and join them.

Before recording: `docker compose up --build`, open http://localhost:8000, set the browser zoom to 125% and keep the deck open in slideshow mode.

---

## Part 1 — Abhinav Kumar (primary member) · slides 1–3 · 0:00–1:10
**Slide 1 — Title (0:00–0:15)**
"Hi, we are team SRMIST_QueueQueueing from SRM Institute of Science and Technology. Our project for Theme 02 is FixFlow: vague complaint in, grounded one-tap fix out."

**Slide 2 — Theme (0:15–0:45)**
- Customers say "my screen flickers and the battery dies fast", not "Settings > Display > Motion smoothness".
- An agent spends about 15 minutes per scenario reading articles and ordering steps, across millions of interactions.
- Then the user still has to find the right screen.
- Our task: a REST API that turns the complaint and its knowledge article into ordered JSON steps, each Settings step with an exact one-tap deeplink, in under 300 ms for known issues.

**Slide 3 — Existing solutions & gaps (0:45–1:10)**
- Manual triage is slow, and keyword search still leaves the work to the user.
- Generic LLM chatbots invent steps and web links and point to the wrong or parent menu. Decision trees don't scale to 10k scenarios.
- "So we designed FixFlow to be grounded, exact, safe, instant and verifiable." Hand over to Abhishek.

## Part 2 — Abhishek Verma · slides 4–6 · 1:10–2:30
**Slide 4 — Solution & architecture (1:10–1:40)**
- Walk the pipeline left to right: cache → enrichment → grounded extraction → deeplink mapping → contract gate → JSON API.
- Two guarantees: every step must cite the article, and code rejects anything it can't find there; every deeplink is copied verbatim from the official catalog.
- If the LLM is down, the same pipeline runs with a rules parser, so it never fails.

**Slide 5 — Demo (switch to the browser, 1:40–2:20)**
- Open `localhost:8000/?sample=18`: the "inputs delayed, touch laggy" complaint → plan appears, least disruptive first.
- Click **Open**, then **Verify** on "Enable Touch Sensitivity" → "✓ Verified … Touch sensitivity is True".
- Point at the engine view: cache hit, 0 ms, $0.
- Type an unseen paraphrase, "my taps take ages to register on the touchscreen" → same kind of plan from the cache in milliseconds.

**Slide 6 — Tech stack (2:20–2:30)**
"Python 3.12 with FastAPI and Pydantic, the official schema unchanged; Gemini Flash-Lite; local CPU embeddings with BM25; SQLite cache; Docker; 53 tests." Hand over to Ayushi.

## Part 3 — Ayushi Paul · slides 7–9 · 2:30–3:40
**Slide 7 — Impact & use case (2:30–2:55)**
- Three uses: customer self-service in a voice assistant or support app; agent assist (15 minutes → milliseconds); compiling the whole knowledge base once and serving millions of repeats at $0.
- Impact numbers: 100% catalog-valid links, 0 invented web links.

**Slide 8 — Innovation, results & limitations (2:55–3:25)**
- Innovation: citation-verified extraction, action- and depth-aware deeplinks, Tap → Verify, symptom-guarded cache, outage-proof design.
- Results: all automated gates 100% on the official and both held-out sets; step accuracy 2.60 of 3 on the official lines and 2.73 on the final held-out set; an independent LLM judge gives 1.94 and 2.06; 87.5% of unseen paraphrases get the same-article plan in under 100 ms.
- Limitations, said honestly: on our final never-tuned paraphrase set the cache reaches only 75% hits (target 80%); the LLM sometimes drops an article section; the judge itself is noisy.

**Slide 9 — What's next (3:25–3:40)**
"Compile the full 10k+ article base, learn the best order from telemetry, verify on real devices, and add Hindi/Hinglish." Hand over to Ketki.

## Part 4 — Ketki Gonnade · slides 10–12 · 3:40–4:40
**Slide 10 — Differentiation (3:40–4:10)**
- Measured, not claimed: held-out sets, gold labels, an LLM judge and a 3-way ablation. The hybrid mapper reaches 100% precision vs 75% for full-LLM mapping and 58% for keyword rules, at $0.
- Outage-proof, proven: during the Gemini 503 outage, 30 of 32 cold requests fell back and every one stayed contract-valid.
- Show the no-match case in the browser: `localhost:8000/?sample=5` (tablet dark, multi-window article) → "the article doesn't cover this, so nothing is invented."

**Slide 11 — Checklist (4:10–4:25)**
Public repo, README with `docker compose up`, this video, the deck in PPTX and PDF, all in the tagged commit `PRISM_GENAI_HACKATHON_Y2026`.

**Slide 12 — Thank you (4:25–4:40)**
"FixFlow: grounded, exact, safe, instant and verifiable. Thank you from team SRMIST_QueueQueueing."

---

## Final-round live demo (15 Oct, if shortlisted)
Same split. Keep `docker compose up` running before the session starts, and have `?sample=18`, `?sample=5` and `?sample=16` (three complaints in one line) open in tabs. Rehearse the Q&A: why not let the LLM pick deeplinks (ablation + catalog integrity), what happens when the LLM is down (rules fallback), how it scales to 10k (batch compile + cache).
