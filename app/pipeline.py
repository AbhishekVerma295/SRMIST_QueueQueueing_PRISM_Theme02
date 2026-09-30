"""End-to-end orchestration: cache -> enrichment -> extraction -> relevance -> mapping/compile -> gate."""
import copy
import re
import time

import numpy as np

from . import cache as cache_mod
from . import config, embed, llm, llm_stages, validators
from .compile import compile_goal
from .enrich_rules import enrich, split_intents, symptoms_of, variations
from .extract_rules import clean_siis, extract

MODEL_NAME = "rules-offline+bge-small-en-v1.5"
ACTION_MIN_RELEVANCE = 0.52          # weakly related reference text: keep only clearly relevant sections
ACTION_MIN_RELEVANCE_STRONG = 0.45   # reference text is clearly about this complaint: keep its sections
MAX_ACTIONS = 6

_cache: cache_mod.SemanticCache | None = None


def get_cache() -> cache_mod.SemanticCache:
    global _cache
    if _cache is None:
        _cache = cache_mod.SemanticCache()
    return _cache


def coerce_siis(siis) -> tuple[str | None, str]:
    """Accepts a raw string or the kit's {title, content} object. Returns (content, title)."""
    if siis is None:
        return None, ""
    if isinstance(siis, dict):
        content = str(siis.get("content") or siis.get("text") or "")
        title = str(siis.get("title") or "")
    else:
        content, title = str(siis), ""
    content = content[: config.MAX_SIIS_CHARS].strip()
    if not title and content:
        m = re.search(r"\b([A-Z][^():]{8,90}?)\s*\(\s*[A-Z][\w ,]+\)\s*:", content[:400])
        title = m.group(1).strip() if m else content.split("\n")[0][:90]
    return (content or None), title


def _envelope(query: str, qvars: list[str], contexts: list[dict], t0: float, cache_hit: bool, model: str, fallback: str | None = None) -> dict:
    meta = {"latency_ms": int(round((time.perf_counter() - t0) * 1000)), "cache_hit": cache_hit, "model": model, "cost_usd": 0.0}
    if fallback:
        meta["fallback"] = fallback
    return {"query": query, "query_variations": qvars, "response": {"contexts": contexts}, "meta": meta}


def _relevance(qv: np.ndarray, texts: list[str]) -> np.ndarray:
    return embed.embed(texts) @ qv if texts else np.zeros(0)


def plan_intent(intent: str, content: str, title: str, trace: dict) -> dict | None:
    e = enrich(intent, title)
    qv = embed.embed_one(f"{e.text} {e.phrase}")
    ir, _ = extract(content)
    cleaned = clean_siis(content)
    doc_rel = float(max(_relevance(qv, [title or cleaned[:120], cleaned[:600]])))
    # symptom evidence: the title names the complaint's symptom, or the body mentions it at least twice
    body_hits = sum(len(re.findall(s[1], cleaned, re.IGNORECASE)) for s in symptoms_of(e.text))
    symptom_match = bool({s[0] for s in symptoms_of(title)} & set(e.symptom_ids)) or body_hits >= 2
    if symptom_match:
        doc_rel = max(doc_rel, 0.75)          # reference title names the same symptom
    item = {"intent": intent, "topic": e.topic, "doc_relevance": round(doc_rel, 3), "symptom_match": symptom_match, "actions": []}
    trace.setdefault("intents", []).append(item)
    needed = config.DOC_MIN_RELEVANCE if symptom_match else max(config.DOC_MIN_RELEVANCE, 0.70)
    if doc_rel < needed or not ir:
        item["decision"] = "no_match"
        return None
    rels = _relevance(qv, [f"{a.heading}. {' '.join(a.steps[:3])}" for a in ir])
    min_rel = ACTION_MIN_RELEVANCE_STRONG if doc_rel >= 0.74 else ACTION_MIN_RELEVANCE
    keep = []
    for a, r in zip(ir, rels):
        generic = a.kind in ("critical", "escalation")
        ok = r >= min_rel or (generic and doc_rel >= 0.65)
        item["actions"].append({"kind": a.kind, "target": a.target or a.heading, "rel": round(float(r), 3), "kept": bool(ok)})
        if ok:
            keep.append((float(r) + (0.2 if a.kind == "settings" else 0.0), a))
    top = {id(a) for _, a in sorted(keep, key=lambda t: -t[0])[:MAX_ACTIONS]}
    chosen = [a for a in ir if id(a) in top]            # back to source order
    goal = compile_goal(e, chosen, doc_rel, MAX_ACTIONS)
    item["decision"] = "plan" if goal else "no_actions"
    return goal


def troubleshoot(query: str, siis_response=None, debug: bool = False, use_cache: bool = True, lookup: bool = True) -> dict:
    t0 = time.perf_counter()
    query = (query or "")[: config.MAX_QUERY_CHARS]
    content, title = coerce_siis(siis_response)
    s_hash = cache_mod.siis_hash(f"{title}\n{content}") if content else None
    trace: dict = {}
    cache = get_cache()

    if use_cache and lookup:
        hit, how, sim = cache.lookup(query, s_hash)
        trace["cache"] = {"how": how, "similarity": round(sim, 3)}
        if hit:
            env = copy.deepcopy(hit)
            env["query"] = query
            if how != "exact":   # variations must paraphrase *this* query, not the cached one (rules mode: ~1 ms)
                env["query_variations"] = variations(enrich(split_intents(query)[0], title))
            env["meta"] = {"latency_ms": int(round((time.perf_counter() - t0) * 1000)), "cache_hit": True, "model": hit["meta"].get("model", MODEL_NAME), "cost_usd": 0.0}
            if hit["meta"].get("fallback"):
                env["meta"]["fallback"] = hit["meta"]["fallback"]
            if debug:
                env["trace"] = trace
            return env

    intents = split_intents(query)
    primary = enrich(intents[0], title)

    # L2: look up the normalised complaint (catches vague or oddly phrased inputs, e.g. no-SIIS one-liners)
    if use_cache and lookup and primary.canonical.lower() != query.lower():
        hit, how, sim = cache.lookup(primary.canonical, s_hash, rerank_query=query)
        trace["cache_l2"] = {"how": how, "similarity": round(sim, 3), "key": primary.canonical}
        if hit:
            env = copy.deepcopy(hit)
            env["query"] = query
            env["query_variations"] = variations(primary)
            env["meta"] = {"latency_ms": int(round((time.perf_counter() - t0) * 1000)), "cache_hit": True, "model": hit["meta"].get("model", MODEL_NAME), "cost_usd": 0.0}
            if hit["meta"].get("fallback"):
                env["meta"]["fallback"] = hit["meta"]["fallback"]
            if debug:
                env["trace"] = trace
            return env

    if not content:
        env = _envelope(query, variations(primary), [], t0, False, MODEL_NAME, "no_siis_context")
        if debug:
            env["trace"] = trace
        return env

    model, cost, canonical_keys = MODEL_NAME, 0.0, [primary.canonical]
    contexts: list[dict] = []
    extracted = None
    qvars = None
    if llm.enabled():
        usage, (llm_canonical, llm_vars), extracted = llm_stages.run_parallel(query, content, title, trace)
        cost = usage.cost_usd
        trace["llm"] = {"calls": usage.calls, "tokens_in": usage.tokens_in, "tokens_out": usage.tokens_out, "ms": round(usage.ms), "errors": usage.errors}
        qvars = llm_stages.complete_variations(query, llm_vars, primary)
        if llm_canonical:
            canonical_keys.append(llm_canonical)
        if extracted is not None:
            model = f"{usage.model or llm.model_name()}+bge-small-en-v1.5"
            for e, actions, rel in extracted:
                if rel == "no" or not actions:
                    continue
                goal = compile_goal(e, actions, 0.9 if rel == "yes" else 0.7, MAX_ACTIONS)
                if goal:
                    _add_context(contexts, goal)
    if extracted is None:                     # no key, or the LLM call failed: offline rules path
        if llm.enabled():
            model = MODEL_NAME + " (llm fallback)"
        for intent in intents:
            goal = plan_intent(intent, content, title, trace)
            if goal:
                _add_context(contexts, goal)
    qvars = qvars or variations(primary)

    # final gate: drop any context that still violates the contract (should not happen)
    safe = []
    for g in contexts:
        problems = validators.check_goal(g)
        if problems:
            trace.setdefault("gate_rejections", []).append(problems)
        else:
            safe.append(g)
    env = _envelope(query, qvars, safe, t0, False, model, None if safe else "no_match")
    env["meta"]["cost_usd"] = cost
    if use_cache and config.CACHE_WRITE and (safe or extracted is not None):
        keys = [*canonical_keys, *qvars]
        tier = "auto" if safe and all(g["score"] >= 0.5 for g in safe) else "provisional"
        cache.store(query, s_hash, {k: env[k] for k in ("query_variations", "response", "meta")}, keys, primary.symptom_ids, tier=tier)
    if debug:
        env["trace"] = trace
    return env


def _add_context(contexts: list[dict], goal: dict) -> None:
    """Adds a goal unless an earlier one has the same title or exactly the same actions (multi-intent merge)."""
    names = [a["actionName"] for a in goal["actions"]]
    if all(goal["title"] != c["title"] and names != [a["actionName"] for a in c["actions"]] for c in contexts):
        contexts.append(goal)
