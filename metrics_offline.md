# System Performance Metrics & Evaluation Report
**Mode:** offline rules (forced)
**Model(s) on the cold path:** rules-offline+bge-small-en-v1.5 x32
**Embeddings:** BAAI/bge-small-en-v1.5 (ONNX, CPU)
**Environment:** 16 vCPU / Windows 11 / Python 3.12.10
**Data:** official Theme 2 kit (D1, 20 lines; results.jsonl), held-out D2 (12 scenarios, 4 domains), paraphrase sets D3/D3b. Generated 2026-09-28 21:40

---

## 1. Schema & Rule Compliance
| Metric | Target | D1 official (results.jsonl) | D2 held-out (cold) |
| :--- | :--- | :--- | :--- |
| Schema-valid output lines | >= 99% | 100.0% | 100.0% |
| Rule compliance (Goal / Title / Description syntax) | >= 95% | 100.0% | 100.0% |
| Absolute URL leaks | 0 | 0 | 0 |
| Deeplink catalog validity (exact URI match) | 100% | 100.0% | 100.0% |
| Auto actions carrying valid actionable deeplink | >= 90% | 100.0% | 100.0% |

D1: plans 17/20 · actions 58 (auto 6, dummy_positive 3) · full envelope valid 100.0%.
D2: plans 10/12 · actions 26 (auto 13, dummy_positive 1) · full envelope valid 100.0%.

---

## 2. Accuracy Benchmarks
| Evaluation Metric | Scale / Anchor | D1 official | D2 held-out |
| :--- | :--- | :--- | :--- |
| Step accuracy (completeness, correctness, ordering) — automatic proxy* | 0.0 - 3.0 | 2.20 (17) | 2.88 (10) |
| Deeplink relevance (exact target screen vs. parent menu) | 0.0 - 2.0 | 2.00 (3) | 1.71 (14) |
| Deeplink precision (emitted catalog links that gold expects) | 0 - 100% | 100.0% (0 spurious of 3) | 100.0% (0 spurious of 12) |
| Abstention accuracy (no_match exactly when the reference text doesn't fit) | 0 - 100% | 90.0% | 100.0% |

D1 is scored on results.jsonl (the shipped, pre-warmed plans). The same D1 lines re-run cold in this mode score: step accuracy 2.34, deeplink relevance 2.00, precision 100.0%, abstention 95.0%.
*Step-accuracy proxy = required gold actions found (0-1) + emitted actions that gold expects (0-1) + contract order respected (0-1); actions match by exact deeplink id or fuzzy name (token-set ratio >= 70). Gold labels: D1 by one annotator (Claude, spot-check pending); D2 written with its reference texts.

---

## 3. Latency Benchmarks (N >= 30 requests per path)
| Execution Path | Target (P95) | P50 (ms) | P95 (ms) |
| :--- | :--- | :--- | :--- |
| Cache hit - exact query match (N=38) | <= 300 ms | 0 | 0 |
| Cache hit - unseen semantic paraphrase (N=22, D3b held-out, no siis) | <= 300 ms | 16 | 46 |
| Cold query - full pipeline extraction & mapping (N=32, D1 + D2) | <= 8000 ms | 91 | 132 |

---

## 4. Operational Cost & Cache Efficacy
| Metric Item | Target | Measured Value |
| :--- | :--- | :--- |
| Cold query average inference cost | Tracked | $0.00000 per LLM-served cold query (0 of 32 cold runs used the LLM; the rest fell back to rules at $0) |
| Cache hit inference cost | $0.00 | $0.00 |
| Semantic cache hit rate (on unseen paraphrases) | >= 80% | 81.8% hit; 59.1% same-article plan (strict), 81.8% same-symptom plan (22 held-out hand-written paraphrases, D3b) |
| False hits on unrelated complaints | 0 | 1 of 10 |
| Tuning set D3 (for reference; thresholds were set on it) | - | 95.6% hit, 80.0% correct, 0 false hits of 20 |
| Cost derivation method | - | (prompt tokens x input rate + completion tokens x output rate), rates from .env (LLM_PRICE_*_PER_1M) |

---

## 5. Architectural Ablation Analysis
| Architecture Variant | Step Accuracy | Latency (P95) | Cost / Query | Key Observations |
| :--- | :--- | :--- | :--- | :--- |
| Baseline: Full LLM Deeplink Mapping | TBD | TBD | TBD | Phase 3 |
| Variant A: Hybrid BM25 + Dense Embedding Retrieval | TBD | TBD | TBD | current default mapper |
| Variant B: Pure Rules-Based Deeplink Mapping | TBD | TBD | TBD | Phase 3 |

---

## 6. Known Edge Cases & System Limitations
* The LLM provider was heavily overloaded while these numbers were produced (HTTP 503 "high demand" on most Flash/Flash-Lite models). The engine then tries other models and finally falls back to offline rules, so every request still returns a contract-valid plan. The model mix above shows how often each path served.
* Contract rule "critical actions last" puts service-centre escalation before restarts/resets.
* input.txt line 17 holds three complaints. Each becomes its own intent; intents that yield an identical plan are merged.
* Paraphrase thresholds were tuned on D3; D3b was written afterwards and is reported untouched.
* D2 was used for one round of error analysis (28 Sep). It exposed four general bugs, three of them fixed: a selected option read as a deeper menu, "turn it off" not read as switching off, a "Restart on schedule" setting treated as a disruptive restart, and an open-screen bonus outranking an exact phrase match. D2 is therefore a development set, not a strict held-out set.
* "Optimize now" (a button label) does not reach the catalog's "Optimize Device Performance" entry; the engine falls back to the placeholder link.
* Offline rules relevance is coarse (e.g. row_16 abstains although the blank-display article partly fits). The LLM path decides relevance per problem.

**Paraphrase misses (D3b held-out):** 'apps like the stock search make my screen go plain white with no words'; 'big inner screen of the fold is gone - no picture and no touch response, small outer one ok'; "the picture on my brand-new phone's screen looks warped, can I get a diagnostic?"; 'my taps take ages to register on the touchscreen'

**False hits (D3b negatives):** "the flashlight won't turn on"
