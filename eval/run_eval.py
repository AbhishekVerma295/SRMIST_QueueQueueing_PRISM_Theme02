"""Evaluation harness v0 -> metrics.md (Appendix C template of the Theme 2 spec).

Measures now: schema/rule gates, URL leaks, catalog validity, auto-action deeplink coverage,
latency percentiles (N>=30 per path), cost, and — once eval/gold/d1_gold.json has reviewed rows —
deeplink relevance (0-2) and abstention accuracy. Step accuracy (0-3), unseen-paraphrase hit rate and
the 3-way ablation are filled in Phase 2/3.
"""
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CACHE_DB", str(ROOT / ".tmp" / "eval_cache.sqlite"))
from app import catalog, config, kit, pipeline, validators  # noqa: E402
from app.text import has_url, is_sentence_case, is_title_case  # noqa: E402


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))] if xs else float("nan")


def rule_ok(goal: dict) -> bool:
    if not validators.GOAL_RE.match(goal["goal"]) or not (2 <= len(goal["title"].split()) <= 3 and is_sentence_case(goal["title"])):
        return False
    return all(is_title_case(a["actionName"]) and a["description"].startswith("It will") and 5 <= len(a["description"].split()) <= 7
               for a in goal["actions"])


def gates(envs: list[dict]) -> dict:
    cat = catalog.get()
    schema_ok = sum(1 for e in envs if not validators.check_schema(e["response"]))
    goals = [g for e in envs for g in e["response"]["contexts"]]
    leaks = sum(1 for e in envs for s in validators._strings(e["response"]) if has_url(s))
    links = [sg["actionableDeeplink"]["deeplink"] for g in goals for a in g["actions"] for sg in a["stepGroups"] if sg.get("actionableDeeplink")]
    autos = [a for g in goals for a in g["actions"] if a["category"] == "auto"]
    auto_ok = sum(1 for a in autos if all(sg.get("actionableDeeplink") and sg["actionableDeeplink"]["deeplink"] in cat.valid_uris for sg in a["stepGroups"]))
    dummy = sum(1 for link in links if link == config.DUMMY_DEEPLINK)
    return {
        "lines": len(envs), "plans": sum(1 for e in envs if e["response"]["contexts"]), "goals": len(goals),
        "actions": sum(len(g["actions"]) for g in goals), "auto_actions": len(autos),
        "schema_valid": schema_ok / len(envs), "rule_compliance": (sum(rule_ok(g) for g in goals) / len(goals)) if goals else 1.0,
        "url_leaks": leaks, "catalog_valid": (sum(1 for link in links if link in cat.valid_uris) / len(links)) if links else 1.0,
        "auto_with_link": (auto_ok / len(autos)) if autos else 1.0, "dummy_links": dummy,
        "full_envelope_valid": sum(1 for e in envs if not validators.check_envelope(e)) / len(envs),
    }


def gold_scores(envs: list[dict]) -> dict | None:
    path = ROOT / "eval" / "gold" / "d1_gold.json"
    if not path.exists():
        return None
    gold = [g for g in json.loads(path.read_text(encoding="utf-8")) if g.get("reviewed")]
    if not gold:
        return None
    cat = catalog.get()
    by_id = {e.id: e for e in cat.entries}
    id_of = {e.raw["deeplink"]: e.id for e in cat.entries}
    by_query = {e["query"]: e for e in envs}
    rel_scores, abst_ok = [], 0
    for g in gold:
        env = by_query.get(g["query"])
        if env is None:
            continue
        got_plan = bool(env["response"]["contexts"])
        abst_ok += got_plan == g["relevant"]
        got_ids = {id_of.get((sg.get("actionableDeeplink") or {}).get("deeplink")) for c in env["response"]["contexts"] for a in c["actions"] for sg in a["stepGroups"]}
        for exp in g["expected_actions"]:
            if not exp.get("deeplink_id") or exp["deeplink_id"] == "DL-DUMMY":
                continue
            ok_ids = {exp["deeplink_id"], *exp.get("acceptable_deeplink_ids", [])}
            if got_ids & ok_ids:
                rel_scores.append(2)
            else:   # same feature (e.g. on/off twin or same validation key) = partial credit
                feats = {by_id[i].feature for i in ok_ids if i in by_id}
                rel_scores.append(1 if any(by_id[i].feature in feats for i in got_ids if i in by_id) else 0)
    return {"rows": len(gold), "abstention_accuracy": abst_ok / len(gold), "deeplink_relevance": (sum(rel_scores) / len(rel_scores)) if rel_scores else None, "deeplinks_scored": len(rel_scores)}


def latency() -> dict:
    cache = pipeline.get_cache()
    cache.clear()
    lines = [(q, kit.match_siis(q)) for q in kit.input_queries()]
    cold = []
    for q, row in lines:                       # cold path, cache off (N = 20 lines, repeated to N>=30)
        for _ in range(2):
            t = time.perf_counter()
            pipeline.troubleshoot(q, row["siis_response"] if row else None, use_cache=False)
            cold.append((time.perf_counter() - t) * 1000)
    for q, row in lines:                       # warm the cache
        pipeline.troubleshoot(q, row["siis_response"] if row else None)
    exact = []
    for _ in range(2):
        for q, row in lines:
            t = time.perf_counter()
            env = pipeline.troubleshoot(q, row["siis_response"] if row else None)
            if env["meta"]["cache_hit"]:
                exact.append((time.perf_counter() - t) * 1000)
    return {"cold": cold, "exact": exact}


def main() -> None:
    envs = [json.loads(line) for line in (ROOT / "results.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    g = gates(envs)
    gs = gold_scores(envs)
    lat = latency()
    fmt = lambda x: f"{x * 100:.1f}%"  # noqa: E731
    p = lambda xs, q: f"{pct(xs, q):.0f}" if xs else "n/a"  # noqa: E731
    md = f"""# System Performance Metrics & Evaluation Report
**Model(s):** {pipeline.MODEL_NAME} (offline rules mode; LLM cold path arrives in Phase 2)
**Embeddings:** {config.EMBED_MODEL} (ONNX, CPU)
**Environment:** {os.cpu_count()} vCPU / {platform.system()} {platform.release()} / Python {platform.python_version()}
**Data:** official kit, {g['lines']} input lines (results.jsonl), generated {time.strftime('%Y-%m-%d %H:%M')}

---

## 1. Schema & Rule Compliance
Evaluated on the official input lines. Held-out scenarios arrive in Phase 2.

| Metric | Target | Measured Value |
| :--- | :--- | :--- |
| Schema-valid output lines | >= 99% | {fmt(g['schema_valid'])} |
| Rule compliance (Goal / Title / Description syntax) | >= 95% | {fmt(g['rule_compliance'])} |
| Absolute URL leaks | 0 | {g['url_leaks']} |
| Deeplink catalog validity (exact URI match) | 100% | {fmt(g['catalog_valid'])} |
| Auto actions carrying valid actionable deeplink | >= 90% | {fmt(g['auto_with_link'])} |

Plans: {g['plans']}/{g['lines']} lines · goals {g['goals']} · actions {g['actions']} (auto {g['auto_actions']}, dummy_positive links {g['dummy_links']}) · full envelope valid {fmt(g['full_envelope_valid'])}

---

## 2. Accuracy Benchmarks
| Evaluation Metric | Scale / Anchor | Score |
| :--- | :--- | :--- |
| Step accuracy (completeness, correctness, ordering) | 0.0 - 3.0 | TBD (Phase 2 judge) |
| Deeplink relevance (exact target screen vs. parent menu) | 0.0 - 2.0 | {f"{gs['deeplink_relevance']:.2f} ({gs['deeplinks_scored']} links, {gs['rows']} reviewed rows)" if gs and gs['deeplink_relevance'] is not None else 'TBD (gold labels pending)'} |
| Abstention accuracy (no_match when the reference text doesn't fit) | 0 - 100% | {fmt(gs['abstention_accuracy']) if gs else 'TBD (gold labels pending)'} |

---

## 3. Latency Benchmarks (N >= 30 requests per path)
| Execution Path | Target (P95) | P50 (ms) | P95 (ms) |
| :--- | :--- | :--- | :--- |
| Cache hit - exact query match (N={len(lat['exact'])}) | <= 300 ms | {p(lat['exact'], 50)} | {p(lat['exact'], 95)} |
| Cache hit - unseen semantic paraphrase | <= 300 ms | TBD (Phase 2 paraphrase set) | TBD |
| Cold query - full pipeline extraction & mapping (N={len(lat['cold'])}) | <= 8000 ms | {p(lat['cold'], 50)} | {p(lat['cold'], 95)} |

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
* The starter kit is the majority copy from public participant repos (see starter_kit/SOURCE.md), not the official distribution.
"""
    (ROOT / "metrics.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
