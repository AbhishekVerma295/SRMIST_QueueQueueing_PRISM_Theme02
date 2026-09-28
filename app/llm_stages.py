"""LLM Stage 0 (enrichment) and Stage 1 (grounded extraction), with programmatic verification.

The LLM never chooses deeplinks and never writes free text that bypasses the contract:
  * every extracted step must cite numbered sentences of the reference text, and is dropped unless the
    cited sentences actually contain its content words (grounding check in code);
  * titles/topics/descriptions are validated and repaired programmatically, falling back to rules output;
  * deeplink mapping, ordering and the final contract gate stay deterministic (compile.py / validators.py).
"""
import re
from concurrent.futures import ThreadPoolExecutor

from . import llm
from .enrich_rules import Enriched, enrich as rules_enrich, variations as rules_variations, _typo
from .extract_rules import IRAction, clean_siis, sections
from .text import STOPWORDS, is_sentence_case, normalize, scrub_urls, sentence_case, title_case, tokens

REGISTERS = ["formal", "casual", "keyword-only", "frustrated", "typo-inclusive"]
CRITICAL_KINDS = ["restart", "force_restart", "safe_mode", "software_update", "reset_settings", "factory_reset"]
GENERIC_STEP_WORDS = {"tap", "open", "navigate", "go", "select", "press", "hold", "swipe", "turn", "check", "try", "use",
                      "make", "sure", "ensure", "then", "again", "next", "screen", "button", "icon", "settings", "app"}

ENRICH_SYSTEM = """You normalise customer complaints about smartphones and tablets for a troubleshooting engine.
Rules:
- canonical_query: one short technical sentence (max 25 words) naming the device (exactly as the user wrote it, or "smartphone"/"tablet"), the symptom and any trigger.
- variations: 8 to 10 distinct paraphrases of the SAME complaint, covering all registers: formal, casual, keyword-only, frustrated, typo-inclusive (real typos).
- Keep device and brand names exactly as the user wrote them. Never add brand names the user did not use. No URLs."""

ENRICH_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "canonical_query": {"type": "STRING"},
        "variations": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "register": {"type": "STRING", "enum": REGISTERS}, "text": {"type": "STRING"}}, "required": ["register", "text"]}},
    },
    "required": ["canonical_query", "variations"],
}

EXTRACT_SYSTEM = """You turn a reference troubleshooting article into structured, grounded troubleshooting plans.
You receive a customer complaint and the article split into numbered sentences [S1], [S2], ... (headings shown as '##').
1. Split the complaint into its distinct problems (usually one; a numbered list or "X and Y" can hold several).
2. For each problem decide if the article contains a viable fix: "yes", "partial" (some sections apply) or "no".
3. For relevant problems list at most 6 actions, most useful first, using ONLY article sentences that address THIS problem. Skip unrelated sections.
Action rules:
- One action = one screen or one physical activity. Steps on the same Settings screen belong to one action.
- kind: "settings" (done in a Settings screen), "manual" (physical checks, cleaning, charging, using another device/app),
  "escalation" (contact support / service center / repair), "critical" (restart, force restart, safe mode, software update, reset, factory reset).
- settings_path: the Settings menu path exactly as the article names it, without "Settings" itself, e.g. ["Display", "Touch sensitivity"]. Empty unless kind is settings or a critical action done in Settings.
- toggle: the switch being turned on/off, if any, else "". op: on | off | view | update | none.
- steps: short imperative instructions, ONE interaction each (split "tap A, then tap B" into two), copied or minimally rewritten from the article. Every step lists the sentence numbers it comes from in cites. Never add steps, tips, links or knowledge that are not in the article.
- name: 2-6 word Title Case action name. benefit: 3-5 word phrase saying what it achieves (e.g. "turn on touch sensitivity").
4. topic: 1-3 word Title Case name of the problem (e.g. "Touchscreen", "Black Screen"). title: 2-3 words, sentence case (e.g. "Touchscreen response issues"). request_type: "Troubleshooting" for faults, "Configuration" for how-to/preference requests.
Keep names neutral: do not introduce brand names that are not in the article or complaint. No URLs."""

EXTRACT_SCHEMA = {
    "type": "OBJECT",
    "properties": {"problems": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "text": {"type": "STRING"}, "topic": {"type": "STRING"}, "title": {"type": "STRING"},
        "request_type": {"type": "STRING", "enum": ["Troubleshooting", "Configuration"]},
        "relevant": {"type": "STRING", "enum": ["yes", "partial", "no"]}, "reason": {"type": "STRING"},
        "actions": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "kind": {"type": "STRING", "enum": ["settings", "manual", "escalation", "critical"]},
            "critical_kind": {"type": "STRING", "enum": CRITICAL_KINDS + ["none"]},
            "name": {"type": "STRING"}, "benefit": {"type": "STRING"},
            "settings_path": {"type": "ARRAY", "items": {"type": "STRING"}},
            "toggle": {"type": "STRING"},
            "op": {"type": "STRING", "enum": ["on", "off", "view", "update", "none"]},
            "steps": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                "text": {"type": "STRING"}, "cites": {"type": "ARRAY", "items": {"type": "INTEGER"}}}, "required": ["text", "cites"]}},
        }, "required": ["kind", "name", "steps"]}},
    }, "required": ["text", "relevant", "actions"]}}},
    "required": ["problems"],
}


def numbered_sentences(content: str) -> tuple[str, list[str]]:
    """Renders the article as '## heading' lines plus [S1].. sentences; returns (prompt_text, sentences)."""
    lines, sents = [], []
    for sec in sections(content):
        if sec.heading:
            lines.append(f"## {sec.heading}")
        for s in sec.sentences:
            sents.append(s)
            lines.append(f"[S{len(sents)}] {s}")
    return "\n".join(lines), sents


def _content_tokens(text: str) -> set:
    return {t for t in tokens(text) if t not in GENERIC_STEP_WORDS and t not in STOPWORDS and len(t) > 2}


def grounded(step: str, cited: list[str]) -> bool:
    """A step is grounded if most of its content words occur in the sentences it cites."""
    if not cited:
        return False
    src = _content_tokens(" ".join(cited)) | {t for t in tokens(" ".join(cited))}
    words = _content_tokens(step)
    if not words:                                   # e.g. "Navigate to and open Settings." -> must cite a Settings sentence
        return any(re.search(r"(?i)settings|power|restart|button", c) for c in cited)
    return len(words & src) / len(words) >= 0.6


def llm_enrich(query: str, usage: llm.Usage) -> tuple[str | None, list[str] | None]:
    out = llm.call_json(ENRICH_SYSTEM, f"Complaint: {query}", ENRICH_SCHEMA, usage, max_tokens=900)
    if not out:
        return None, None
    canonical = scrub_urls(normalize(out.get("canonical_query", "")))[:300] or None
    vs, seen = [], {normalize(query).lower()}
    for v in out.get("variations", []):
        t = scrub_urls(normalize(v.get("text", "")))
        if t and t.lower() not in seen and len(t) <= 300:
            seen.add(t.lower())
            vs.append(t)
    return canonical, vs


def _fix_topic(topic: str, fallback: str) -> str:
    topic = re.sub(r"(?i)\b(troubleshooting|configuration|issues?|problems?)\b", "", normalize(topic)).strip(" -:")
    words = topic.split()
    return title_case(" ".join(words[:3])) if 1 <= len(words) <= 4 and re.fullmatch(r"[\w &/+-]+", topic) else fallback


def _fix_title(title: str, fallback: str) -> str:
    title = sentence_case(normalize(title).rstrip("."))
    return title if 2 <= len(title.split()) <= 3 and is_sentence_case(title) else fallback


def llm_extract(query: str, content: str, title: str, usage: llm.Usage, trace: dict) -> list[tuple[Enriched, list[IRAction], str]] | None:
    """Returns [(enriched_problem, verified_actions, relevance)] or None if the LLM is unavailable."""
    prompt_text, sents = numbered_sentences(content)
    user = f"Complaint: {query}\n\nArticle title: {title}\nArticle:\n{prompt_text}"
    out = llm.call_json(EXTRACT_SYSTEM, user, EXTRACT_SCHEMA, usage, max_tokens=3000)
    if not out:
        return None
    results = []
    dropped = []
    for prob in out.get("problems", [])[:4]:
        ptext = normalize(prob.get("text") or query)
        base = rules_enrich(ptext, title)
        base.topic = _fix_topic(prob.get("topic", ""), base.topic)
        base.title = _fix_title(prob.get("title", ""), base.title)
        if prob.get("request_type") in ("Troubleshooting", "Configuration"):
            base.request_type = prob["request_type"]
        rel = prob.get("relevant", "no")
        actions: list[IRAction] = []
        for a in prob.get("actions", [])[:6]:
            steps, cites = [], []
            for s in a.get("steps", []):
                txt = scrub_urls(normalize(s.get("text", "")))
                ids = [i for i in s.get("cites", []) if isinstance(i, int) and 1 <= i <= len(sents)]
                if txt and grounded(txt, [sents[i - 1] for i in ids]):
                    steps.append(txt)
                    cites.extend(i - 1 for i in ids)
                else:
                    dropped.append(txt[:80])
            if not steps:
                continue
            kind = a.get("kind", "manual")
            ck = a.get("critical_kind") if a.get("critical_kind") in CRITICAL_KINDS else None
            if kind == "critical" and not ck:
                ck = "restart"
            path = [normalize(p) for p in a.get("settings_path", []) if normalize(p) and normalize(p).lower() != "settings"]
            op = a.get("op") if a.get("op") in ("on", "off", "view", "update") else ("view" if path else None)
            ir = IRAction(kind=kind if kind in ("settings", "manual", "escalation", "critical") else "manual",
                          heading=normalize(a.get("name", "")), steps=steps, cites=sorted(set(cites)),
                          path=path, op=op, critical_kind=ck if kind == "critical" else None,
                          toggle=normalize(a.get("toggle", "")) or None)
            if ir.kind == "settings" and not ir.path and not ir.toggle:
                ir.kind = "manual"                       # a Settings action must name its screen
            ir.benefit = normalize(a.get("benefit", "")) or None
            actions.append(ir)
        results.append((base, actions, rel))
    trace["llm_extract"] = {"problems": [{"text": b.text[:80], "relevant": r, "actions": len(a)} for b, a, r in results],
                            "dropped_ungrounded_steps": dropped}
    return results


def run_parallel(query: str, content: str | None, title: str, trace: dict) -> tuple[llm.Usage, tuple, list | None]:
    """Runs enrichment and extraction concurrently (latency ~= one call)."""
    usage = llm.Usage()
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_en = pool.submit(llm_enrich, query, usage)
        f_ex = pool.submit(llm_extract, query, content, title, usage, trace) if content else None
        enriched = f_en.result()
        extracted = f_ex.result() if f_ex else None
    return usage, enriched, extracted


def complete_variations(query: str, llm_vars: list[str] | None, fallback: Enriched) -> list[str]:
    """8-10 distinct variations; guarantees a typo-inclusive one and tops up from the rules generator."""
    out, seen = [], {normalize(query).lower()}
    for v in (llm_vars or [])[:9] + [_typo(fallback.text)] + rules_variations(fallback):
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out[:10]
