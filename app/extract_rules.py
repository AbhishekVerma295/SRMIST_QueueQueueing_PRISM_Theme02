"""Offline Stage 1: rules-based structure extraction from SIIS reference text (no LLM).

Produces an intermediate representation (IR): a list of candidate actions, each with imperative steps
and the indices of the source sentences they came from (citations). Nothing is invented: every step
is a rewrite of a sentence (or a Settings path) found in the reference text.
"""
import re
from dataclasses import dataclass, field

from .text import ensure_period, normalize, scrub_urls, split_sentences

IMPERATIVE_VERBS = {
    "press", "tap", "turn", "go", "open", "remove", "check", "inspect", "insert", "shine", "connect", "charge",
    "wipe", "clean", "disable", "enable", "increase", "decrease", "adjust", "try", "contact", "visit", "swipe",
    "select", "clear", "update", "back", "restart", "reboot", "reset", "hold", "unplug", "plug", "use", "set",
    "make", "ensure", "install", "uninstall", "delete", "navigate", "launch", "switch", "toggle", "disconnect",
    "reinsert", "examine", "look", "avoid", "keep", "move", "place", "drag", "release", "wait", "boot", "run",
    "perform", "schedule", "take", "bring", "replace", "lower", "reduce", "close", "force", "download", "sign",
    "log", "verify", "confirm", "choose", "slide", "attach", "detach", "change",
}
LEAD_INS = re.compile(
    r"^(?:(?:first|next|then|now|finally|also|additionally|alternatively|afterwards|after that|to do this|to fix this|"
    r"if so|otherwise|in this case)\s*,?\s*)+|^(?:please|kindly|simply|just)\s+|^(?:you can|you may|you should|you need to|"
    r"we recommend that you|we recommend you|it is recommended to|let's|let us)\s+(?:also\s+)?(?:try\s+(?:to\s+)?)?",
    re.IGNORECASE,
)
SETTINGS_PATH_RE = re.compile(
    r"(?:go to|open|navigate to|launch|head to|access)\s+(?:the\s+)?(?:device\s+)?Settings(?:\s+app)?\s*(?P<rest>(?:,|>|then|and| )[^.]*)",
    re.IGNORECASE,
)
PATH_STEP_RE = re.compile(r"(?:>|,\s*(?:and\s+)?(?:then\s+)?tap|\bthen\s+tap|\btap(?: on)?|\bselect)\s+(?:the\s+)?(?:switch next to\s+)?(?P<item>[A-Z0-9][\w'&/+-]*(?:\s+[\w'&/+-]+){0,5}?)(?=\s*(?:,|>|\.|$| and | then | to | if ))")
DISRUPTIVE_RE = re.compile(r"(?i)\b(force(?:d)? (?:a )?restart|restart|reboot|power (?:it )?off and (?:back )?on|turn (?:it|the device|your device) off and (?:back )?on|safe mode|factory (?:data )?reset|reset (?:all )?settings|reset network|software update|update the software|firmware|wipe cache|remove the battery)\b")
ESCALATION_RE = re.compile(r"(?i)\b(service cent(?:er|re)|contact (?:us|samsung|techcorp|customer|support|the manufacturer|your)|(?:samsung|techcorp|customer) support|repair service|schedule a repair|walk-in|technician|require service|requires service|visit (?:a|an|the)\b)")
TOGGLE_ON_RE = re.compile(r"(?i)\b(turn on|turned on|enable|switch on|activate|tap the switch(?:es)? next to|toggle on)\b")
TOGGLE_OFF_RE = re.compile(r"(?i)\b(turn off|disable|switch off|deactivate|toggle off)\b")
ADJUST_RE = re.compile(r"(?i)\b(adjust|increase|decrease|lower|raise|set)\b")
HEADING_RE = re.compile(r"^\s*#{1,6}\s*(.+)$")
STEP_PREFIX_RE = re.compile(r"^(?:step\s*\d+\s*[:.)-]\s*|\d+\s*[.)]\s*)", re.IGNORECASE)
NON_ACTION_HEADINGS = re.compile(r"(?i)^(understanding|about|overview|introduction|summary|note|why|what causes|how .* works)")


@dataclass
class IRAction:
    kind: str                 # settings | manual | escalation | critical
    heading: str
    steps: list = field(default_factory=list)
    cites: list = field(default_factory=list)
    path: list = field(default_factory=list)     # Settings path elements, e.g. ["Display", "Touch sensitivity"]
    op: str | None = None                          # on | off | view | update
    critical_kind: str | None = None
    toggle: str | None = None                      # feature whose switch is flipped, e.g. "Swipe for split screen"

    @property
    def target(self) -> str | None:
        """Most specific screen/feature of the action (used for deeplink resolution)."""
        return self.toggle or (self.path[-1] if self.path else None)


@dataclass
class Section:
    heading: str
    sentences: list


def clean_siis(content: str) -> str:
    content = content.replace("\r", "")
    # Drop the category preamble: "Smartphone,Tablet ... Title ( Smartphone,...):"
    m = re.match(r"^[^\n]{0,400}?\):\s*", content)
    if m and "," in m.group(0)[:120]:
        content = content[m.end():]
    return scrub_urls(content)


def sections(content: str) -> list[Section]:
    secs: list[Section] = [Section("", [])]
    for line in clean_siis(content).split("\n"):
        line = line.strip()
        if not line:
            continue
        h = HEADING_RE.match(line)
        if h:
            secs.append(Section(normalize(STEP_PREFIX_RE.sub("", h.group(1).strip("# :"))), []))
            continue
        line = re.sub(r"(?<=[a-z0-9)])\.(?=[A-Z])", ". ", line)   # 'view.When' -> 'view. When'
        secs[-1].sentences.extend(normalize(s) for s in split_sentences(line))
    return [s for s in secs if s.sentences]


def to_imperative(sentence: str) -> str | None:
    s = LEAD_INS.sub("", sentence.strip()).strip()
    s = LEAD_INS.sub("", s).strip()
    if not s:
        return None
    first = s.split()[0].lower().strip(",")
    if first in IMPERATIVE_VERBS:
        return ensure_period(s[0].upper() + s[1:])
    # "If X, do Y" / "For devices with ..., do Y" -> keep only when the main clause is imperative
    m = re.match(r"^(if|for|when|once|after|before)\b[^,]{3,120},\s*(?P<main>.+)$", s, re.IGNORECASE)
    if m:
        main = LEAD_INS.sub("", m.group("main")).strip()
        if main and main.split()[0].lower() in IMPERATIVE_VERBS:
            return ensure_period(s[0].upper() + s[1:])
    return None


def settings_path(sentence: str) -> list[str] | None:
    m = SETTINGS_PATH_RE.search(sentence)
    if not m:
        return None
    items = [normalize(x.group("item")).strip(" ,") for x in PATH_STEP_RE.finditer(m.group("rest"))]
    items = [re.sub(r"(?i)^(?:the\s+)?switch next to\s+", "", i) for i in items if i and i.lower() not in {"settings", "restart"}]
    return items or None


def path_steps(path: list[str], op: str | None) -> list[str]:
    steps = ["Navigate to and open Settings."]
    for item in path[:-1]:
        steps.append(f"Tap on {item}.")
    last = path[-1]
    if op == "on":
        steps.append(f"Tap the switch next to {last} to turn it on.")
    elif op == "off":
        steps.append(f"Tap the switch next to {last} to turn it off.")
    else:
        steps.append(f"Tap on {last}.")
    return steps


def _op_for(sentence: str) -> str:
    if TOGGLE_OFF_RE.search(sentence):
        return "off"
    if TOGGLE_ON_RE.search(sentence):
        return "on"
    if ADJUST_RE.search(sentence):
        return "update"
    return "view"


def _critical_kind(sentence: str) -> str:
    s = sentence.lower()
    if "factory" in s:
        return "factory_reset"
    if "reset" in s:
        return "reset_settings"
    if "safe mode" in s:
        return "safe_mode"
    if "update" in s or "firmware" in s:
        return "software_update"
    if "force" in s or "battery" in s or ("hold" in s and ("volume" in s or "power" in s or "side" in s)):
        return "force_restart"
    return "restart"


FILLER_RE = re.compile(r"(?i)\b(together|go through some|see if we can|help (?:you )?resolve this|here's how|the following steps|as follows|refer to (?:our|the)|for more information)\b")
OPEN_SETTINGS_RE = re.compile(r"(?i)^(?:please\s+)?(?:navigate to and open|open|go to|navigate to|launch)\s+(?:the\s+)?Settings(?:\s+app)?\.?$")
UI_STEP_RE = re.compile(r"(?i)^(?:tap|select|swipe|toggle|choose|slide|drag|enter|scroll)\b")
TAP_ITEM_RE = re.compile(r"(?i)^(?:tap|select|choose)\s+(?:on\s+)?(?:the\s+)?(?P<item>[A-Z0-9][^.,]{0,60}?)(?:\s+(?:to|and|then|from|under|at)\b.*|,.*)?\.?$")
CRITICAL_HEADING_RE = re.compile(r"(?i)\b(restart\w*|reboot\w*|safe mode|factory|reset\w*|software updates?|update (?:the|your) (?:software|device)|firmware)\b")
ESCALATION_STEP = "Contact Customer Support or visit an authorized Service Center."   # wording of the official sample_output
SWITCH_RE = re.compile(r"(?i)switch(?:es)? next to\s+(?P<feat>[A-Z][^.,]{1,50}?)(?=\s+(?:or|to|and|if)\b|[.,]|$)")


COMPOUND_RE = re.compile(r"(?i),?\s*(?:and\s+)?then\s+(?=[a-z])|,\s+(?=(?:tap|select|swipe|press|drag|open|choose|toggle)\b)|;\s+")


def split_compound(step: str) -> list[str]:
    """One physical interaction per step: 'Tap A, tap B, and then tap C.' -> three steps."""
    if re.match(r"(?i)^(if|for|when|once|after|before)\b", step):
        return [step]
    parts = [p.strip(" ,.") for p in COMPOUND_RE.split(step) if p and p.strip(" ,.")]
    parts = [re.sub(r"(?i)^and\s+", "", p) for p in parts]
    if len(parts) > 1 and all(p.split()[0].lower() in IMPERATIVE_VERBS for p in parts):
        return [ensure_period(p[0].upper() + p[1:]) for p in parts]
    return [step]


def _tap_item(step: str) -> str | None:
    m = TAP_ITEM_RE.match(step.strip())
    return normalize(m.group("item")).strip(" .") if m else None


def extract(content: str) -> tuple[list[IRAction], list[Section]]:
    """Returns candidate actions in source order plus the parsed sections (for relevance scoring).

    One Action = One Screen: a Settings path (inline "go to Settings > Display > X" or spread over
    "Open Settings. Tap Display. Tap X." sentences) plus the UI taps that follow it form one action.
    Sections whose heading names a disruptive operation become one critical action.
    """
    secs = sections(content)
    actions: list[IRAction] = []
    escalation = IRAction("escalation", "Service")
    sid = 0
    for sec in secs:
        heading = sec.heading or ""
        if NON_ACTION_HEADINGS.match(heading):
            sid += len(sec.sentences)
            continue
        crit_kind = _critical_kind(heading) if CRITICAL_HEADING_RE.search(heading) and "app" not in heading.lower() else None
        manual = IRAction("critical" if crit_kind else "manual", heading, critical_kind=crit_kind)
        current: IRAction | None = None          # open settings action that absorbs follow-up taps
        for sent in sec.sentences:
            sid += 1
            cite = sid - 1
            if FILLER_RE.search(sent):
                continue
            path = settings_path(sent)
            if path:
                op = _op_for(sent)
                current = IRAction("critical" if crit_kind else "settings", heading, path_steps(path, op), [cite], path, op, crit_kind)
                actions.append(current)
                continue
            if OPEN_SETTINGS_RE.match(sent.strip()):
                current = IRAction("critical" if crit_kind else "settings", heading, ["Navigate to and open Settings."], [cite], [], "view", crit_kind)
                actions.append(current)
                continue
            step = to_imperative(sent)
            if current is not None and step and UI_STEP_RE.match(step):
                item = _tap_item(step)
                sw = SWITCH_RE.search(step)
                walking = len(current.steps) - 1 == len(current.path) and step.lower().startswith("tap")
                if item and walking and not re.match(r"(?i)(?:the\s+)?switch", item):
                    current.path.append(item)     # still walking down the menu
                if sw:
                    current.toggle = normalize(sw.group("feat"))
                # only an explicit switch (or a toggle of the screen itself) changes the action's operation;
                # "Select Buttons to turn off gestures" is a choice made on the same screen
                names_target = bool(current.path) and current.path[-1].lower() in step.lower()
                if sw or names_target:
                    if TOGGLE_OFF_RE.search(step):
                        current.op = "off"
                    elif TOGGLE_ON_RE.search(step) or sw:
                        current.op = "on"
                current.steps.append(step)
                current.cites.append(cite)
                continue
            current = None
            if not step or len(step.split()) > 45:
                if ESCALATION_RE.search(sent) and re.search(r"(?i)service|contact|repair", sent):
                    escalation.steps.append(ESCALATION_STEP)
                    escalation.cites.append(cite)
                continue
            if ESCALATION_RE.search(sent):
                escalation.steps.append(step)
                escalation.cites.append(cite)
            elif not crit_kind and DISRUPTIVE_RE.search(sent):
                kind = _critical_kind(sent)
                actions.append(IRAction("critical", heading, [step], [cite], critical_kind=kind))
            else:
                manual.steps.append(step)
                manual.cites.append(cite)
        if manual.steps:
            manual.steps = list(dict.fromkeys(manual.steps))[:7]
            actions.append(manual)
    # drop settings actions that never reached a screen, dedupe same-screen actions (keep first)
    seen_paths: set = set()
    out: list[IRAction] = []
    for a in actions:
        if a.kind == "settings":
            if not a.path:
                continue
            key = tuple(p.lower() for p in a.path)
            if key in seen_paths:
                continue
            seen_paths.add(key)
        out.append(a)
    if escalation.steps:
        escalation.steps = list(dict.fromkeys(escalation.steps))[:4]
        out.append(escalation)
    for a in out:
        a.steps = list(dict.fromkeys(s for step in a.steps for s in split_compound(step)))[:8]
        # "Software Updates" sections that only talk about third-party app updates are not disruptive
        if a.critical_kind == "software_update" and not re.search(r"(?i)software update|system|firmware|One UI", " ".join(a.steps)):
            a.kind, a.critical_kind = "manual", None
    return out, secs
