"""Contract checks shared by the runtime gate, the tests and the evaluation harness.

Each check returns a list of human-readable violations; an empty list means compliant.
"""
import re

from . import catalog as catalog_mod
from . import config, kit
from .text import has_url, is_sentence_case, is_title_case

GOAL_RE = re.compile(r"^Follow these steps to perform this .+ (Troubleshooting|Configuration)$")
CRITICAL = "critical"


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def check_schema(response: dict) -> list[str]:
    try:
        kit.schema().ContextDeeplinkResponse.model_validate(response)
        return []
    except Exception as exc:  # pydantic.ValidationError
        return [f"schema: {str(exc).splitlines()[0]}"]


def check_goal(goal: dict) -> list[str]:
    v: list[str] = []
    cat = catalog_mod.get()
    valid_uris = cat.valid_uris
    if not GOAL_RE.match(goal.get("goal", "")):
        v.append(f"goal syntax: {goal.get('goal')!r}")
    title = goal.get("title", "")
    if not 2 <= len(title.split()) <= 3 or not is_sentence_case(title):
        v.append(f"title must be 2-3 words sentence case: {title!r}")
    score = goal.get("score")
    if not isinstance(score, float) or not 0.0 <= score <= 1.0:
        v.append(f"score must be a float in [0,1]: {score!r}")
    seen_critical = False
    for a in goal.get("actions", []):
        name, desc, cat_ = a.get("actionName", ""), a.get("description", ""), a.get("category")
        if not is_title_case(name):
            v.append(f"actionName not Title Case: {name!r}")
        n = len(desc.split())
        if not desc.startswith("It will") or not 5 <= n <= 7:
            v.append(f"description must be 5-7 words starting 'It will': {desc!r} ({n})")
        if cat_ not in ("auto", "manual", "critical"):
            v.append(f"bad category: {cat_!r}")
        if cat_ == CRITICAL:
            seen_critical = True
        elif seen_critical:
            v.append(f"non-critical action after a critical one: {name!r}")
        if not a.get("stepGroups"):
            v.append(f"action without stepGroups: {name!r}")
        for g in a.get("stepGroups", []):
            if not g.get("steps"):
                v.append(f"empty steps in {name!r}")
            ad, vd = g.get("actionableDeeplink"), g.get("validationDeeplink")
            if cat_ == "manual" and ad:
                v.append(f"manual action carries a deeplink: {name!r}")
            if cat_ == "auto" and not ad:
                v.append(f"auto action without actionable deeplink: {name!r}")
            if ad and ad.get("deeplink") not in valid_uris:
                v.append(f"deeplink not in catalog: {ad.get('deeplink')!r}")
            if ad and ad.get("deeplink") in cat.by_uri:
                entry = cat.by_uri[ad["deeplink"]].raw
                for f in ("description", "message", "originalType"):
                    if ad.get(f) != entry.get(f):
                        v.append(f"actionableDeeplink.{f} not copied verbatim for {ad['deeplink']}")
                if vd and vd != {k: (entry.get("validation") or {}).get(k) for k in ("deeplink", "key", "resultType", "condition", "value")}:
                    v.append(f"validationDeeplink not copied verbatim for {ad['deeplink']}")
    for s in _strings(goal):
        if has_url(s):
            v.append(f"URL leak: {s[:80]!r}")
    return v


def check_envelope(env: dict) -> list[str]:
    v: list[str] = []
    for k in ("query", "query_variations", "response", "meta"):
        if k not in env:
            v.append(f"missing top-level key {k!r}")
    qv = env.get("query_variations", [])
    if not 8 <= len(qv) <= 10 or len({q.lower() for q in qv}) != len(qv):
        v.append(f"query_variations must be 8-10 distinct items (got {len(qv)})")
    resp = env.get("response", {})
    v += check_schema(resp)
    for g in resp.get("contexts", []):
        v += check_goal(g)
    meta = env.get("meta", {})
    for k, t in (("latency_ms", (int, float)), ("cache_hit", bool), ("model", str), ("cost_usd", (int, float))):
        if not isinstance(meta.get(k), t):
            v.append(f"meta.{k} missing or wrong type")
    if not resp.get("contexts") and meta.get("fallback") not in ("no_match", "no_siis_context", "invalid_request", "internal_error"):
        v.append("empty contexts without meta.fallback")
    for s in _strings(env.get("response", {})):
        if has_url(s):
            v.append("URL leak in response")
            break
    return v


def is_dummy(link: dict | None) -> bool:
    return bool(link) and link.get("deeplink") == config.DUMMY_DEEPLINK
