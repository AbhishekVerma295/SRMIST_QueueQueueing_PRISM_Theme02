"""Offline Stage 0: query enrichment without an LLM.

Normalises the complaint, splits multi-intent inputs, extracts slots (device, symptom, domain, trigger)
and produces 8-10 deterministic query variations across registers
(formal, casual, keyword-only, frustrated, typo-inclusive).
"""
import hashlib
import re
from dataclasses import dataclass, field

from .text import normalize, sentence_case, title_case

# id, regex, goal topic, title (2-3 words, sentence case), domain, noun phrase, request type
SYMPTOMS = [
    ("screen_damage", r"crack|shatter|broken (?:screen|glass|display)|bleeding|screen (?:is )?broken", "Screen Damage", "Screen display damage", "Display", "a cracked screen", "Troubleshooting"),
    ("touch", r"touch(?:screen)?\b[^.]{0,40}\b(?:doesn't|does not|not|isn't|won't|stopped|lag|delay|unresponsive)|inputs? (?:are )?delayed|ghost touch|respond(?:ing)? to touch|touch responsiveness|unresponsive (?:touch|screen)", "Touchscreen", "Touchscreen response issues", "Display", "an unresponsive touchscreen", "Troubleshooting"),
    ("flicker", r"flicker|flash(?:es|ing)?\b|blink", "Screen Flicker", "Screen flickering issue", "Display", "a flickering screen", "Troubleshooting"),
    ("distortion", r"half (?:black|dark)|one side of the (?:display|screen)|lines on|distort|green line|pink line|colou?r(?:ed)? lines", "Display Distortion", "Distorted screen display", "Display", "a distorted display", "Troubleshooting"),
    ("screen_size", r"screen (?:stays )?small|doesn't fill|does not fill|not full screen|expand it to full size|full size", "Display Size", "Screen size settings", "Display", "a screen that does not fill the display", "Configuration"),
    ("floating_button", r"floating (?:circle|button|icon|bubble)|hovers on my screen", "Assistant Menu", "Floating button settings", "Accessibility", "a floating shortcut button", "Configuration"),
    ("black_screen", r"black|blank|dark|no display|nothing (?:is )?(?:visible|on the screen)|won't turn on|doesn't display|can hardly see|hardly see anything|white screen|blue (?:\(or black\) )?screen|no image", "Black Screen", "Blank screen display", "Display", "a blank or black screen", "Troubleshooting"),
    ("battery_drain", r"battery (?:dies|drain|drains|draining|runs out)|battery[^.]{0,20}fast|charge doesn't last|battery life", "Battery Drain", "Battery fast drain", "Battery", "fast battery drain", "Troubleshooting"),
    ("charging", r"not charging|won't charge|charging (?:slow|slowly|issue|problem)|charges slowly", "Charging", "Charging problems", "Battery", "charging problems", "Troubleshooting"),
    ("overheating", r"overheat|too hot|heats up|getting hot|gets hot", "Overheating", "Device overheating issue", "Performance", "overheating", "Troubleshooting"),
    ("slow", r"\bslow\b|laggy|\blags?\b|freez|hangs?\b|stutter|sluggish", "Slow Performance", "Slow device performance", "Performance", "slow performance", "Troubleshooting"),
    ("camera", r"camera|photos?\b|pictures?\b|blurry", "Camera", "Camera quality issues", "Camera", "camera problems", "Troubleshooting"),
    ("transfer", r"smart switch|transfer(?:ring)? (?:my )?data|qr code", "Data Transfer", "Smart Switch transfer", "Performance", "a failing data transfer", "Troubleshooting"),
    ("email", r"e-?mail|gmail|outlook", "Email Access", "Email access issues", "Connectivity", "email loading problems", "Troubleshooting"),
    ("rotation", r"rotat", "Screen Rotation", "Screen rotation issues", "Display", "a screen that won't rotate", "Troubleshooting"),
    ("navigation", r"swipe|gesture|navigation bar", "Swipe Navigation", "Swipe navigation settings", "Display", "swipe gesture problems", "Troubleshooting"),
]
_SYMPTOM_RES = [(s, re.compile(s[1], re.IGNORECASE)) for s in SYMPTOMS]

DEVICE_RE = re.compile(
    r"\b(?:Samsung\s+)?Galaxy\s+(?:Z\s+)?(?:Flip|Fold|Tab|Note|S|A|M)(?![a-z])\s?\d{0,2}(?:\s?(?:Ultra|Plus|FE|\+))?(?:/[A-Z]?\d{2})?"
    r"|\bSamsung\s+(?:S\*+|[A-Z]\d{2,4}[A-Z]?)(?:\s+Ultra)?",
    re.IGNORECASE,
)
TRIGGER_RE = re.compile(r"\b(after|when|whenever|while|every time)\s+([^,.;]{3,70})", re.IGNORECASE)
NUMBERED_RE = re.compile(r'(?:^|\s)\d+\.\s*"?(.+?)"?(?=\s+\d+\.\s|$)')


@dataclass
class Enriched:
    raw: str
    text: str
    device: str
    symptom_ids: list = field(default_factory=list)
    topic: str = "Device"
    title: str = "Device issue help"
    domain: str = "General"
    phrase: str = "a device problem"
    request_type: str = "Troubleshooting"
    trigger: str | None = None

    @property
    def canonical(self) -> str:
        trig = f" {self.trigger}" if self.trigger else ""
        return f"{self.domain} issue on {self.device}: {self.phrase}{trig}"

    @property
    def goal(self) -> str:
        return f"Follow these steps to perform this {self.topic} {self.request_type}"


def split_intents(query: str) -> list[str]:
    """'1. "A" 2. "B" 3. "C"' -> ["A", "B", "C"]; anything else -> [query]."""
    q = normalize(query)
    if re.match(r'^\s*1\.\s', q):
        parts = [normalize(p).strip(' "') for p in NUMBERED_RE.findall(q)]
        parts = [p for p in parts if len(p.split()) >= 3]
        if parts:
            return parts
    return [q]


def clean_query(query: str) -> str:
    q = normalize(query)
    q = re.sub(r'^\s*\d+\.\s*', "", q).strip(' "')
    return q


def symptoms_of(text: str) -> list[tuple]:
    return [s for s, rx in _SYMPTOM_RES if rx.search(text)]


def enrich(query: str, siis_title: str | None = None) -> Enriched:
    q = clean_query(query)
    dev = DEVICE_RE.search(q)
    device = normalize(dev.group(0)) if dev else ("Galaxy tablet" if re.search(r"(?i)tablet", q) else "Galaxy phone")
    e = Enriched(raw=query, text=q, device=device)
    found = symptoms_of(q)
    if found:
        e.symptom_ids = [s[0] for s in found]
        _, _, e.topic, e.title, e.domain, e.phrase, e.request_type = found[0]
    elif siis_title:
        core = re.split(r"(?i)\s+(?:on|for|with)\s+(?:a|an|the|your)?\s*(?:samsung|galaxy)", siis_title)[0]
        core_words = core.split()[:3]
        e.topic = title_case(" ".join(core_words))
        e.title = sentence_case(" ".join(w.lower() for w in core_words[:3])) if len(core_words) >= 2 else sentence_case(core + " issue")
        e.phrase = core.lower()
    t = TRIGGER_RE.search(q)
    if t:
        e.trigger = f"{t.group(1).lower()} {t.group(2).strip()}"
    return e


def _typo(text: str) -> str:
    """Deterministic keyboard-slip typos in up to 3 longer words."""
    ws = text.split()
    idx = [i for i, w in enumerate(ws) if len(w) > 4 and w.isalpha()]
    h = int(hashlib.md5(text.encode()).hexdigest(), 16)
    for k, i in enumerate(sorted(idx, key=lambda i: (h >> (i % 60)) & 0xFF)[:3]):
        w = ws[i]
        j = 1 + (h >> (k * 3)) % (len(w) - 2)
        ws[i] = w[:j] + w[j + 1] + w[j] + w[j + 2:]
    return " ".join(ws).lower()


def variations(e: Enriched) -> list[str]:
    dev, phrase = e.device, e.phrase
    bare = re.sub(r"^(?:a|an)\s+", "", phrase)
    first_clause = re.split(r"[,;—]| so | and I ", e.text)[0].strip()
    kw = " ".join(dict.fromkeys(w for w in re.findall(r"[a-z0-9]+", (dev + " " + bare).lower()) if w not in {"a", "the", "that", "does", "not"}))
    cands = [
        f"My {dev} is experiencing {phrase}. How can I resolve this?",                       # formal
        f"hey my {dev.lower()} has {phrase} rn, what do i do",                                 # casual
        f"{kw} fix",                                                                          # keyword-only
        f"This is so frustrating, my {dev} keeps showing {phrase} and nothing helps!",        # frustrated
        _typo(e.text),                                                                        # typo-inclusive
        f"Why does my {dev} have {phrase}?",
        first_clause if first_clause.lower() != e.text.lower() else f"{dev}: {bare}",
        f"How do I fix {phrase} on my Samsung {('tablet' if 'tab' in (dev + e.text).lower() else 'phone')}?",
        f"Troubleshooting {bare} on a Galaxy device",
        f"{sentence_case(bare)} again?? need help asap",
    ]
    out: list[str] = []
    seen = {e.text.lower()}
    for c in cands:
        c = normalize(c)
        if c and c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out[:10]
