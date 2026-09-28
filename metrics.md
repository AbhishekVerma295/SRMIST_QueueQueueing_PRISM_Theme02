# System Performance Metrics & Evaluation Report
**Model(s):** rules-offline+bge-small-en-v1.5 (offline rules mode; LLM cold path arrives in Phase 2)
**Embeddings:** BAAI/bge-small-en-v1.5 (ONNX, CPU)
**Environment:** 16 vCPU / Windows 11 / Python 3.12.10
**Data:** official kit, 20 input lines (results.jsonl), generated 2026-09-28 19:55

---

## 1. Schema & Rule Compliance
Evaluated on the 20 official input lines (official Theme 2 kit). Held-out scenarios arrive in Phase 2.

| Metric | Target | Measured Value |
| :--- | :--- | :--- |
| Schema-valid output lines | >= 99% | 100.0% |
| Rule compliance (Goal / Title / Description syntax) | >= 95% | 100.0% |
| Absolute URL leaks | 0 | 0 |
| Deeplink catalog validity (exact URI match) | 100% | 100.0% |
| Auto actions carrying valid actionable deeplink | >= 90% | 100.0% |

Plans: 16/20 lines · goals 16 · actions 61 (auto 7, dummy_positive links 4) · full envelope valid 100.0%

---

## 2. Accuracy Benchmarks
| Evaluation Metric | Scale / Anchor | Score |
| :--- | :--- | :--- |
| Step accuracy (completeness, correctness, ordering) | 0.0 - 3.0 | TBD (Phase 2 judge) |
| Deeplink relevance (exact target screen vs. parent menu) | 0.0 - 2.0 | 2.00 (3 links, 20 reviewed rows) |
| Deeplink precision (emitted catalog links that gold expects) | 0 - 100% | 100.0% (0 spurious of 3) |
| Abstention accuracy (no_match when the reference text doesn't fit) | 0 - 100% | 95.0% |

---

## 3. Latency Benchmarks (N >= 30 requests per path)
| Execution Path | Target (P95) | P50 (ms) | P95 (ms) |
| :--- | :--- | :--- | :--- |
| Cache hit - exact query match (N=32) | <= 300 ms | 0 | 25 |
| Cache hit - unseen semantic paraphrase | <= 300 ms | TBD (Phase 2 paraphrase set) | TBD |
| Cold query - full pipeline extraction & mapping (N=40) | <= 8000 ms | 111 | 248 |

---

## 4. Operational Cost & Cache Efficacy
| Metric Item | Target | Measured Value |
| :--- | :--- | :--- |
| Cold query average inference cost | Tracked | $0.00 (offline rules mode, no LLM calls) |
| Cache hit inference cost | $0.00 | $0.00 |
| Semantic cache hit rate (on unseen paraphrases) | >= 80% | TBD (Phase 2) |
| Cost derivation method | - | (prompt tokens + completion tokens) x rate |

---

## 5. Architectural Ablation Analysis
| Architecture Variant | Step Accuracy | Latency (P95) | Cost / Query | Key Observations |
| :--- | :--- | :--- | :--- | :--- |
| Baseline: Full LLM Deeplink Mapping | TBD | TBD | TBD | Phase 3 |
| Variant A: Hybrid BM25 + Dense Embedding Retrieval | TBD | TBD | TBD | current default mapper |
| Variant B: Pure Rules-Based Deeplink Mapping | TBD | TBD | TBD | Phase 3 |

---

## 6. Known Edge Cases & System Limitations
* Offline rules mode decides relevance with small-embedding similarity. It abstains on the clearly mismatched reference texts but is coarse. The LLM path (Phase 2) replaces it.
* Contract rule "critical actions last" puts service-centre escalation before restarts/resets.
* input.txt line 17 holds three complaints. Each becomes its own intent; intents that yield an identical plan are merged.
* Gold labels (eval/gold/d1_gold.json) were written from the reference texts by one annotator (Claude); a human spot-check is pending.
* Offline relevance is coarse: row_16 (charger-triggered flashing) abstains although the blank-display article partly fits; the LLM path should fix this.
