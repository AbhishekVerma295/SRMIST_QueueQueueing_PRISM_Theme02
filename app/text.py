"""Text utilities: URL scrubbing, casing rules, word-count fitting, sentence splitting."""
import re
import unicodedata

URL_RE = re.compile(
    r"\[([^\]]*)\]\([^)]*\)"                       # markdown link -> keep label (group 1)
    r"|https?://\S+"
    r"|www\.\S+"
    r"|\b[\w-]+(?:\.[\w-]+)*\.(?:com|net|org|in|co|io|ly|gl|me|info|biz)(?:/\S*)?\b",
    re.IGNORECASE,
)
URL_DETECT_RE = re.compile(r"https?://|www\.|\]\(|\b[\w-]+\.(?:com|net|org|in|co|io|ly|gl|me|info|biz)\b", re.IGNORECASE)

SMALL_WORDS = {"a", "an", "the", "and", "or", "but", "for", "nor", "of", "to", "in", "on", "at", "by", "with", "via", "as", "vs"}
STOPWORDS = SMALL_WORDS | {
    "is", "are", "be", "it", "its", "this", "that", "your", "you", "my", "i", "me", "from", "if", "then", "so",
    "can", "will", "do", "does", "not", "no", "up", "into", "any", "all", "some", "has", "have", "was", "were",
    "settings", "setting", "device", "phone", "tablet", "samsung", "galaxy", "screen", "option", "options", "page",
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("—", "-").replace("–", "-").replace("�", "-")
    return re.sub(r"\s+", " ", text).strip()


def scrub_urls(text: str) -> str:
    """Removes web links; markdown links keep their visible label."""
    def repl(m: re.Match) -> str:
        return m.group(1) if m.group(1) is not None else ""
    out = URL_RE.sub(repl, text)
    out = re.sub(r"\s+([.,;:!?])", r"\1", out)
    return re.sub(r"\s{2,}", " ", out).strip()


def has_url(text: str) -> bool:
    return bool(URL_DETECT_RE.search(text or ""))


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'+-]*", text or "")


def tokens(text: str) -> list[str]:
    """Lower-cased content tokens with light stemming, for lexical matching."""
    out = []
    for w in words(text.lower()):
        if w in STOPWORDS or len(w) < 2:
            continue
        for suf in ("ing", "ness", "es", "ed", "s"):
            if len(w) > 5 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        out.append(w)
    return out


def title_case(text: str) -> str:
    ws = text.split()
    out = []
    for i, w in enumerate(ws):
        if w.isupper() and len(w) > 1:        # keep acronyms (LDI, USB, S Pen)
            out.append(w)
        elif 0 < i < len(ws) - 1 and w.lower() in SMALL_WORDS:
            out.append(w.lower())
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def is_title_case(text: str) -> bool:
    ws = text.split()
    if not ws:
        return False
    for i, w in enumerate(ws):
        if not w[0].isalpha():
            continue
        if i > 0 and w.lower() in SMALL_WORDS:
            continue
        if not w[0].isupper():
            return False
    return True


def sentence_case(text: str) -> str:
    text = text.strip()
    return text[:1].upper() + text[1:] if text else text


def is_sentence_case(text: str) -> bool:
    ws = text.split()
    if not ws or not ws[0][0].isupper():
        return False
    # every later word capitalised = Title Case, not sentence case
    later = [w for w in ws[1:] if w[0].isalpha()]
    return not later or any(w[0].islower() for w in later)


PAD_WORDS = ["on", "your", "device"]


def fit_words(phrase: str, lo: int = 5, hi: int = 7) -> str:
    """Trims or pads a phrase to lo..hi words (programmatic, never trusted to a prompt)."""
    ws = phrase.split()
    trailing_small = SMALL_WORDS | {"your", "you", "the", "and"}
    if len(ws) > hi:
        ws = ws[:hi]
        while len(ws) > lo and ws[-1].lower() in trailing_small:
            ws.pop()
    pads = ["for", "you"] if "your" in [w.lower() for w in ws] else PAD_WORDS
    i = 0
    while len(ws) < lo and i < len(pads):
        ws.append(pads[i])
        i += 1
    while len(ws) < lo:
        ws.append("quickly")
    return " ".join(ws).rstrip(".,;:")


def fit_description(body: str) -> str:
    """'It will ...' with exactly 5-7 words."""
    body = re.sub(r"^\s*it will\s+", "", body.strip(), flags=re.IGNORECASE).rstrip(".")
    return fit_words("It will " + body[:1].lower() + body[1:])


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(])", text)
    return [p.strip() for p in parts if p.strip()]


def ensure_period(step: str) -> str:
    step = step.strip().rstrip(",;:")
    return step if step.endswith((".", "!", "?")) else step + "."
