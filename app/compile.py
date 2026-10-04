"""Stage 2 + contract compiler: IR actions -> schema-valid Goal dicts.

- Deeplink mapping: settings actions resolve their most specific screen/feature in the catalog; the
  entry is copied verbatim (actionable + validation). A real Settings screen missing from the catalog
  gets the catalog's dummy_positive placeholder (description/message written as 5-7 words naming the
  concrete screen, as the catalog's DL-DUMMY entry instructs). Manual actions never carry a deeplink.
- Ordering by disruption: auto -> manual -> escalation -> critical (restart < safe mode < update < reset).
- Every text field is forced into the contract programmatically (casing, 5-7 word "It will" descriptions,
  no URLs, one interaction per step).
"""
import re
from dataclasses import dataclass

from . import catalog as catalog_mod
from . import config
from .enrich_rules import Enriched
from .extract_rules import IRAction
from .text import ensure_period, fit_description, fit_words, has_url, scrub_urls, title_case

CRITICAL_ORDER = {"restart": 0, "force_restart": 1, "safe_mode": 2, "software_update": 3, "reset_settings": 4, "factory_reset": 5}
CRITICAL_NAME = {
    "restart": "Restart Your Device",
    "force_restart": "Force Restart Your Device",
    "safe_mode": "Start Device in Safe Mode",
    "software_update": "Update Device Software",
    "reset_settings": "Reset Device Settings",
    "factory_reset": "Perform Factory Data Reset",
}
CRITICAL_DESC = {
    "restart": "It will restart and refresh your device",
    "force_restart": "It will force an unresponsive device restart",
    "safe_mode": "It will isolate problems caused by apps",
    "software_update": "It will install the latest software fixes",
    "reset_settings": "It will restore default device settings",
    "factory_reset": "It will erase and restore your device",
}
MANUAL_DESC = [
    (r"liquid|damage|inspect|examine|ldi|corrosion", "It will rule out hardware damage"),
    (r"protector|film", "It will remove screen protector interference"),
    (r"charger|cable", "It will rule out a faulty charger"),
    (r"\bcharg", "It will make sure the battery charges"),
    (r"power on|turn it on|powers on", "It will confirm the device powers on"),
    (r"\bclean|\bwipe|\bdust|moisture|\bwet\b", "It will clear dirt affecting the screen"),
    (r"wi-?fi|internet|network|mobile data", "It will restore your network connection"),
    (r"\bmouse\b|\busb\b|computer|\bpc\b", "It will let you reach your data"),
    (r"back ?up|smart switch|transfer", "It will keep your personal data safe"),
    (r"rotat|orientation", "It will restore automatic screen rotation"),
    (r"software update", "It will install the latest software fixes"),
    (r"\bapps?\b|cache|\bupdate", "It will rule out app conflicts"),
    (r"\blight|shutter|camera|video", "It will reduce flicker in your videos"),
]
ESCALATION_NAME = "Contact Customer Support"
ESCALATION_DESC = "It will get your device professionally repaired"


@dataclass
class CompiledAction:
    data: dict
    level: tuple
    confidence: float


def _short_target(t: str, max_words: int = 4) -> str:
    t = re.sub(r"(?i)\s+settings?$", "", t.strip(" .,"))
    return " ".join(t.split()[:max_words])


def _action_name_for_settings(a: IRAction) -> str:
    target = _short_target(a.target or "Settings")
    verb = {"on": "Enable", "off": "Disable", "update": "Adjust"}.get(a.op or "view")
    name = f"{verb} {target}" if verb else f"Open {target} Settings"
    return title_case(name)


def _trim_phrase(text: str, max_words: int) -> str:
    """Cuts at a natural break (comma, 'and', 'to', '(') and never ends on a small word."""
    text = re.split(r",|\(|\?|:|\s+(?:and|then|but|so|if|while|when)\s+", text.strip())[0]
    words = text.split()[:max_words]
    while len(words) > 2 and words[-1].lower() in {"a", "an", "the", "and", "or", "of", "to", "for", "in", "with", "your", "but"}:
        words.pop()
    return " ".join(words)


def _manual_name(a: IRAction) -> str:
    h = re.sub(r"(?i)^(step\s*\d+[:.)-]?\s*|\d+[.)]\s*)", "", a.heading or "").strip(" :.-")
    h = re.sub(r"(?i)^(troubleshooting|understanding|factors affecting)\s+", "Check ", h)
    if not h or h.endswith("?") or len(h.split()) < 2:
        h = a.steps[0].rstrip(".") if a.steps else "Check your device"
    name = _trim_phrase(h, 6) or "Check Your Device"
    return title_case(name)


def _manual_desc(a: IRAction) -> str:
    # the heading names the action's purpose best ("Charger Issues"); steps are only a fallback
    for blob in (a.heading.lower(), " ".join(a.steps).lower()):
        for pat, desc in MANUAL_DESC:
            if re.search(pat, blob):
                return desc
    return "It will help resolve the issue"


def _clean_steps(steps: list[str]) -> list[str]:
    out = []
    for s in steps:
        s = re.sub(r"(?i)\bplease\b,?\s*", "", scrub_urls(s)).strip()      # steps are commands, not requests
        if s and not has_url(s) and len(s.split()) >= 2:
            out.append(ensure_period(s[0].upper() + s[1:]))
    return out


def compile_action(a: IRAction, cat: "catalog_mod.Catalog") -> CompiledAction | None:
    steps = _clean_steps(a.steps)
    if not steps:
        return None
    actionable = validation = None
    confidence = 0.5
    if a.kind == "settings":
        m = cat.match(a.target, a.op, " > ".join(a.path))
        screen_path = a.path if a.toggle and a.path and a.toggle.lower() != a.path[-1].lower() else a.path[:-1]
        if not m.accepted and screen_path and screen_path[-1].lower() != "settings":
            # the target is an option or switch inside a screen the catalog has (e.g. "Buttons" inside Navigation
            # bar): that screen is the one screen this action happens on, so open it instead of a placeholder
            parent = cat.match(screen_path[-1], "view", " > ".join(screen_path))
            if parent.accepted and parent.coverage >= 0.99 and parent.entry.op == "view":
                m, a = parent, IRAction(**{**a.__dict__, "path": list(screen_path), "toggle": None, "op": "view"})
        if m.accepted:
            actionable, validation = cat.actionable(m.entry), cat.validation(m.entry)
            confidence = min(1.0, 0.5 * m.dense + 0.5 * m.coverage + 0.1)
        else:
            parent = a.path[-2] if len(a.path) > 1 else "Settings"
            target = _short_target(a.target)
            actionable = {"deeplink": cat.dummy_uri,
                          "description": fit_words(f"Open the {target} settings screen under {parent}", 5, 7),
                          "message": fit_words(f"Open {target} in {parent} settings", 5, 7),
                          "originalType": (cat.dummy or {}).get("originalType", "placeholder")}
            confidence = 0.45
        category = "auto"
        name = _action_name_for_settings(a)
        verb_desc = {"on": f"turn on {_short_target(a.target, 3)}", "off": f"turn off {_short_target(a.target, 3)}",
                     "update": f"adjust {_short_target(a.target, 3)} for you"}.get(a.op or "view", f"open {_short_target(a.target, 3)} settings directly")
        desc = fit_description(verb_desc.lower())
        level = (0, 0)
    elif a.kind == "critical":
        kind = a.critical_kind or "restart"
        category, name, desc = "critical", CRITICAL_NAME[kind], fit_description(CRITICAL_DESC[kind])
        if a.path:
            m = cat.match(a.target, a.op, " > ".join(a.path))
            if m.accepted and m.coverage >= 0.99:
                actionable, validation = cat.actionable(m.entry), cat.validation(m.entry)
        level = (3, CRITICAL_ORDER.get(kind, 0))
    elif a.kind == "escalation":
        category, name, desc, level = "manual", ESCALATION_NAME, fit_description(ESCALATION_DESC), (2, 0)
    else:
        desc_body = a.benefit if a.benefit else _manual_desc(a)
        category, name, desc, level = "manual", _manual_name(a), fit_description(desc_body), (1, 0)
    data = {
        "actionName": name,
        "description": desc,
        "stepGroups": [{"steps": steps, "actionableDeeplink": actionable, "validationDeeplink": validation}],
        "category": category,
    }
    if category == "manual":
        data["stepGroups"][0]["actionableDeeplink"] = None
        data["stepGroups"][0]["validationDeeplink"] = None
    return CompiledAction(data, level, confidence)


def compile_goal(e: Enriched, actions: list[IRAction], doc_relevance: float, max_actions: int = 6) -> dict | None:
    cat = catalog_mod.get()
    compiled: list[tuple[int, CompiledAction]] = []
    seen_links: set = set()
    seen_names: set = set()
    for i, a in enumerate(actions):
        c = compile_action(a, cat)
        if c is None:
            continue
        link = (c.data["stepGroups"][0]["actionableDeeplink"] or {}).get("deeplink")
        if link and link != cat.dummy_uri:
            if link in seen_links:          # One Action = One Screen: same screen already covered
                continue
            seen_links.add(link)
        if c.data["actionName"] in seen_names:
            continue
        seen_names.add(c.data["actionName"])
        compiled.append((i, c))
    if not compiled:
        return None
    compiled = compiled[:max_actions]
    compiled.sort(key=lambda t: (t[1].level, t[0]))       # stable: source order within a level
    conf = sum(c.confidence for _, c in compiled) / len(compiled)
    score = round(max(0.05, min(0.99, 0.55 * doc_relevance + 0.35 * conf + 0.1 * min(1.0, len(compiled) / 3))), 2)
    return {"goal": e.goal, "title": e.title, "actions": [c.data for _, c in compiled], "score": score}
