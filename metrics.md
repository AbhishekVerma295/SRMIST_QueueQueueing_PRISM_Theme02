# System Performance Metrics & Evaluation Report
**Mode:** LLM cold path + rules fallback
**Model(s) on the cold path:** rules-offline+bge-small-en-v1.5 (llm fallback) x14, gemini-3.1-flash-lite+bge-small-en-v1.5 x7, gemini-3.5-flash-lite+bge-small-en-v1.5 x6, rules-offline+bge-small-en-v1.5 (llm abstained) x4, gemini-3.6-flash+bge-small-en-v1.5 x1
**Embeddings:** BAAI/bge-small-en-v1.5 (ONNX, CPU)
**Environment:** 16 vCPU / Windows 11 / Python 3.12.10
**Data:** official Theme 2 kit (D1, 20 lines; results.jsonl), D2 dev set (12 scenarios), D2b final held-out (10 scenarios, 6 domains incl. 2 mismatched pairs), paraphrase sets D3 (tuning) / D3b (held-out) / D3c (final unseen). Generated 2026-10-03 14:22

---

## 1. Schema & Rule Compliance
| Metric | Target | D1 official (results.jsonl) | D2 dev (cold) | D2b final held-out (cold) |
| :--- | :--- | :--- | :--- | :--- |
| Schema-valid output lines | >= 99% | 100.0% | 100.0% | 100.0% |
| Rule compliance (Goal / Title / Description syntax) | >= 95% | 100.0% | 100.0% | 100.0% |
| Absolute URL leaks | 0 | 0 | 0 | 0 |
| Deeplink catalog validity (exact URI match) | 100% | 100.0% | 100.0% | 100.0% |
| Auto actions carrying valid actionable deeplink | >= 90% | 100.0% | 100.0% | 100.0% |

D1: plans 18/20 · actions 58 (auto 4, dummy_positive 1) · full envelope valid 100.0%.
D2: plans 10/12 · actions 26 (auto 13, dummy_positive 0) · full envelope valid 100.0%.
D2b: plans 9/10 · actions 24 (auto 12, dummy_positive 1) · full envelope valid 100.0%.

---

## 2. Accuracy Benchmarks
| Evaluation Metric | Scale / Anchor | D1 official | D2 dev | D2b final held-out |
| :--- | :--- | :--- | :--- | :--- |
| Step accuracy (completeness, correctness, ordering) — automatic proxy* | 0.0 - 3.0 | 2.60 (17) | 2.95 (10) | 2.73 (8) |
| Step accuracy — LLM judge** | 0.0 - 3.0 | 1.94 (18) | 2.35 (10) | 2.06 (9) |
| Deeplink relevance (exact target screen vs. parent menu) | 0.0 - 2.0 | 2.00 (3) | 1.86 (14) | 1.82 (11) |
| Deeplink precision (emitted catalog links that gold expects) | 0 - 100% | 100.0% (0 spurious of 3) | 100.0% (0 spurious of 13) | 90.9% (1 spurious of 11) |
| Abstention accuracy (no_match exactly when the reference text doesn't fit) | 0 - 100% | 95.0% | 100.0% | 90.0% |

D1 is scored on results.jsonl (the shipped, pre-warmed plans). The same D1 lines re-run cold in this mode score: step accuracy 2.47, deeplink relevance 2.00, precision 100.0%, abstention 95.0%.
*Step-accuracy proxy = required gold actions found (0-1) + emitted actions that gold expects (0-1) + contract order respected (0-1); actions match by exact deeplink id or fuzzy name (token-set ratio >= 70). Gold labels: D1 by one annotator (Claude, spot-check pending); D2 written with its reference texts.
**LLM judge = gemini-3.8-flash (a stronger model than the Flash-Lite plan writer), temperature 0. It sees only the complaint, the reference article and the plan, never our gold labels, and grades completeness, correctness and ordering 0 / 0.5 / 1 each (eval/llm_judge.py, eval/runs/judge.json). D2 and D2b plans for the judge come from the deterministic offline engine.

---

## 3. Latency Benchmarks (N >= 30 requests per path)
| Execution Path | Target (P95) | P50 (ms) | P95 (ms) |
| :--- | :--- | :--- | :--- |
| Cache hit - exact query match (N=40) | <= 300 ms | 0 | 1 |
| Cache hit - unseen semantic paraphrase (N=24, D3b held-out, no siis) | <= 300 ms | 30 | 82 |
| Cold query - full pipeline extraction & mapping (N=32, D1 + D2) | <= 8000 ms | 2367 | 6617 |

---

## 4. Operational Cost & Cache Efficacy
| Metric Item | Target | Measured Value |
| :--- | :--- | :--- |
| Cold query average inference cost | Tracked | $0.00047 per LLM-served cold query (14 of 32 cold runs used the LLM; the rest fell back to rules at $0) |
| Cache hit inference cost | $0.00 | $0.00 |
| Semantic cache hit rate (on unseen paraphrases) | >= 80% | 91.7% hit; 87.5% same-article plan (strict), 91.7% same-symptom plan (24 held-out hand-written paraphrases, D3b) |
| False hits on unrelated complaints | 0 | 0 of 10 |
| Final unseen set D3c (written before the last changes, never tuned on) | >= 80% | 75.0% hit; 62.5% same-article plan, 62.5% same-symptom plan (16 paraphrases); false hits 0 of 10 |
| Tuning set D3 (for reference; thresholds were set on it) | - | 95.8% hit, 93.8% correct, 0 false hits of 20 |
| Cost derivation method | - | (prompt tokens x input rate + completion tokens x output rate), rates from .env (LLM_PRICE_*_PER_1M) |

---

## 5. Architectural Ablation Analysis
| Architecture Variant | Step Accuracy | Latency (P95) | Cost / Query | Key Observations |
| :--- | :--- | :--- | :--- | :--- |
| Baseline: Full LLM Deeplink Mapping | 2.55 (deeplink relevance 1.76, precision 75%) | 6167 ms | $0.00125 | LLM reads the whole catalog and picks an id per action |
| Variant A: Hybrid BM25 + Dense Embedding Retrieval | 2.57 (deeplink relevance 1.88, precision 100%) | 541 ms | $0.00000 | our default: action- and depth-aware rerank, phrase check, $0 |
| Variant B: Pure Rules-Based Deeplink Mapping | 2.55 (deeplink relevance 1.29, precision 58%) | 511 ms | $0.00000 | longest feature-phrase match; cheap but picks wrong screens |

Extraction is held fixed (offline rules) so only the deeplink mapper changes; D1 + D2 cold, scored on gold (eval/ablation.py, eval/runs/ablation.json).

---

## 6. Known Edge Cases & System Limitations
* Shipped plans (results.jsonl, data/derived/cache.sqlite) come from a batch compile on 3 Oct: Gemini Flash-Lite built 16 of 20 official lines. On the 4 lines where the LLM judged the article not relevant, the rules path found a grounded plan and that plan is used (the engine abstains only when both paths say no). Against the first compile (28 Sep) this cache scores higher on gold (step proxy 2.60 vs 2.20, abstention 95% vs 90%) and on the LLM judge's absolute score (1.94 vs 1.85, abstention agreement 89% vs 84%); in blind pairwise comparisons (both orders) the judge is even (6 wins vs 7, 6 ties). Details: eval/runs/judge_compare.json. Gemini compiles vary between runs; a compile with thinking level low scored lower (2.38) and was not shipped.
* Free-tier provider limits: when Gemini is overloaded (HTTP 503) or out of quota (429), the adapter tries other models and then falls back to offline rules, so every request still returns a contract-valid plan. The model mix above shows which path served.
* Contract rule "critical actions last" puts service-centre escalation before restarts/resets.
* input.txt line 17 holds three complaints. Each becomes its own intent; intents that yield an identical plan are merged.
* Paraphrase thresholds were tuned on D3; D3b was written afterwards; D3c and D2b were written on 3 Oct before the final changes and are reported untouched.
* D2 was used for error analysis, so it is a development set; D2b is the strict held-out scenario set.
* row_8 (a TV aspect-ratio article for a phone complaint) still gets a plan from the LLM; gold says the article does not fit.
* Offline rules relevance is coarse (e.g. row_16 abstains although the blank-display article partly fits). The LLM path decides relevance per problem.
* Gold labels for D1 were written by one annotator (Claude) with a human spot-check pending; the LLM judge is reported next to the gold proxy for that reason.
* The LLM judge is itself noisy: with the same complaint and article it sometimes flips its "article has a fix" verdict between runs, and it scores lower than the gold proxy overall (it penalises missing optional sections). We report it as a second opinion, not ground truth.
* D3c (final unseen paraphrases) is below the 80% target: 75% hit, 62.5% same-article plan. Two hits went to the wrong plan through the normalised-complaint (L2) lookup ("pitch black" and "won't light up" got the flicker plan, which shares the black-screen symptom). We did not tune on D3c after seeing this.

**D3c final set:** misses 'random apps turn my screen totally white and empty'; 'foldable main display shows nothing and ignores my fingers, outside screen still fine'; 'My touchscreen responds slowly to every tap.'; 'new phone, picture on the display looks wrong and warped' · false hits none

**Paraphrase misses (D3b held-out):** 'apps like the stock search make my screen go plain white with no words'; "the picture on my brand-new phone's screen looks warped, can I get a diagnostic?"
