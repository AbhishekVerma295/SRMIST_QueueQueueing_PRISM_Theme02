"""Hinglish / Hindi complaints -> plain English, before Stage 0.

Indian users often type in Hinglish (Hindi written in Latin letters, mixed with English words): "screen tut gayi",
"touch kaam nahi kar raha". Everything downstream (symptom list, embeddings, cache keys) is English, so the
complaint is normalised once, at the very start:

  * Hinglish (Latin letters): deterministic rules, offline. Common complaint phrases first ("kaam nahi kar raha"
    -> "is not working"), then a small word list; grammar words are dropped. Same input -> same output.
  * Hindi in Devanagari script: translated by the LLM when a key is set; otherwise left unchanged (reported).
  * English: detected as English and never touched.

The API keeps the user's original text in `query`; the English form only travels inside the pipeline (and the
debug trace), so the contract is unchanged.
"""
import re

from . import llm

DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
WORD_RE = re.compile(r"[a-z]+")

# words that practically never appear in English complaints
STRONG = {"hai", "hain", "nahi", "nhi", "nahin", "raha", "rahi", "rahe", "rha", "rhi", "gaya", "gayi", "gya", "gyi",
          "karta", "karti", "karte", "karke", "mera", "meri", "mere", "mujhe", "kuch", "kuchh", "bahut", "bohot",
          "kaise", "kese", "jata", "jati", "jaata", "jaati", "jate", "hota", "hoti", "wala", "wali", "wale", "lekin",
          "phir", "waqt", "kyun", "kyon", "tut", "toot", "kholte", "kholne", "dikh", "dikhta", "theek", "thik",
          "naya", "naye", "nayi", "poori", "puri", "andar", "bahar", "jagah", "aane", "baja", "badlu", "karu", "karun"}
WEAK = {"ho", "ki", "ka", "ke", "pe", "par", "se", "mein", "me", "aur", "bhi", "toh", "ab", "jab", "kya", "hi"}

_H = r"(?:\s+h(?:ai|ain|e)?)?"           # optional trailing "hai / hain / he / h"
PHRASES = [
    (r"\bcall\s+aane\s+(?:par|pe)\s+ring\s+hota" + _H, " it rings when calls come in "),
    (r"\bring\s+hota" + _H, " it rings "),
    (r"\b(?:on|chalu|start|shuru)\s+(?:nahi|nhi|nahin)\s+ho\s+(?:raha|rahi|rha|rhi|rahe)\b" + _H, " won't turn on "),
    (r"\b(?:on|chalu)\s+karte\s+(?:waqt|samay|time)\b", " while turning on "),
    (r"\bkaam\s+(?:nahi|nhi|nahin)\s+(?:kar\s+(?:raha|rahi|rha|rhi|rahe)|kar\s+pa\s+(?:raha|rahi)|karta|karti|karte)\b" + _H, " is not working "),
    (r"\buse\s+(?:nahi|nhi|nahin)\s+kar\s+pa\s+(?:raha|rahi|rahe|rha|rhi)\b" + _H, " cannot use it "),
    (r"\b(?:garam|garm|gram)\s+ho\s+(?:raha|rahi|jata|jati|jaata|jaati|gaya|gayi)\b" + _H, " is overheating "),
    (r"\b(?:jaldi|jldi)\s+(?:khatam|khtm|down|discharge)\s+ho\s+(?:jati|jaati|jata|jaata|rahi|raha)\b" + _H, " drains very fast "),
    (r"\bcharge\s+(?:nahi|nhi|nahin)\s+ho\s+(?:raha|rahi|rha|rhi)\b" + _H, " is not charging "),
    (r"\b(?:tut|toot|tuut|phoot|foot|fut)\s+(?:gayi|gaya|gyi|gya)\b" + _H, " is cracked "),
    (r"\bcrack\s+ho\s+(?:gayi|gaya|gyi|gya|jati|jaati)\b" + _H, " cracked "),
    (r"\b(?:black|kaali|kali|kaala|kala)\s+ho\s+(?:gayi|gaya|gyi|gya|jati|jaati|jata|jaata)\b" + _H, " went black "),
    (r"\b(?:white|safed|safaid)\s+ho\s+(?:jati|jaati|gayi|gaya|jata|jaata)\b" + _H, " turns white "),
    (r"\bblank\s+ho\s+(?:jati|jaati|gayi|gaya|gyi|gya|jata|jaata)\b" + _H, " goes blank "),
    (r"\bflicker\s+(?:kar\s+(?:rahi|raha)|karti|karta|karke|kar)\b" + _H, " flickers and "),
    (r"\b(?:jhapak|timtima)\w*", " flickers "),
    (r"\bflash\s+(?:hoke|ho\s+ke|ho\s+kar|karke|karti|karta)\b", " flashes and "),
    (r"\b(?:kuch|kuchh)\s+likha\s+(?:nahi|nhi)\s+(?:dikhta|dikhti|dikh\s+raha)\b" + _H, " no text appears "),
    (r"\b(?:kuch|kuchh)\s+(?:bhi\s+)?(?:nahi|nhi|nahin)\s+(?:dikh\s+(?:raha|rahi)|dikhta|dikhti|dikhai\s+deta)\b" + _H, " nothing is visible "),
    (r"\b(?:der|late)\s+(?:se\s+)?respond\s+(?:karta|karti|kar\s+raha|kar\s+rahi)\b" + _H, " responds with a delay "),
    (r"\bhang\s+(?:ho\s+)?(?:raha|rahi|jata|jati|jaata|jaati|gaya|gayi)\b" + _H, " is lagging "),
    (r"\b(?:atak|latak)\s+(?:jata|jati|jaata|jaati|gaya|gayi|raha|rahi)\b" + _H, " gets stuck "),
    (r"\b(?:apne\s+aap\s+)?restart\s+ho\s+(?:jata|jati|jaata|jaati|raha|rahi)\b" + _H, " keeps restarting "),
    (r"\bband\s+ho\s+(?:jate|jaate|jata|jati|jaati|jaata)\b" + _H, " keep closing "),
    (r"\b(?:awaaz|awaz|aawaz|aavaz)\s+(?:nahi|nhi)\s+aa\s+(?:rahi|raha)\b" + _H, " has no sound "),
    (r"\b(connect|transfer|pair)\s+(?:nahi|nhi|nahin)\s+ho\s+(?:raha|rahi|rha|rhi)\b" + _H, r" won't \1 "),
    (r"\bdetect\s+(?:nahi|nhi|nahin)\s+ho\s+(?:raha|rahi|rha|rhi)\b" + _H, " is not detected "),
    (r"\bblur\s+(?:aati|aata|aa\s+rahi)\b" + _H, " is blurry "),
    (r"\bgir\s+(?:gaya|gayi|gya|gyi)\b", " fell "),
    (r"\b(?:nahi|nhi)\s+baja\b", " did not ring "),
    (r"\b(?:kaise|kese)\s+(?:badlu|badlun|change\s+karu|change\s+karun)\b", " how do I change "),
    (r"\b(?:kaise|kese)\s+(?:karu|karun|karein|karen|kare|thik\s+karu|theek\s+karu)\b", " how do I fix "),
    (r"\bkholte\s+hi\b", " as soon as I open "),
    (r"\b(\w+)\s+kholne\s+(?:par|pe)\b", r" when I open \1 "),
    (r"\b(\w+)\s+karne\s+(?:par|pe)\b", r" when I \1 "),
    (r"\b(\w+)\s+karte\s+(?:waqt|samay|time)\b", r" while doing \1 "),
    (r"\b(?:dikh|dikhai\s+de)\s+(?:rahi|raha)\b" + _H, " looks "),
    (r"\b(?:tedhi|tedha|tedhe)\s+(?:medhi|medha|medhe)\b", " distorted "),
    (r"\bandar\s+(?:wali|wala)\s+screen\b", " inner screen "),
    (r"\bbahar\s+(?:wali|wala)\s+screen\b", " outer screen "),
    (r"\bfold\s+(?:wali|wala)\s+jagah\b", " fold crease "),
    (r"\b(\w+)\s+(?:wale|wala|wali)\s+step\b", r" \1 step "),
    (r"\bphir\s+se\b", " again "),
    (r"\bbaar\s+baar\b", " repeatedly "),
]
PHRASES = [(re.compile(p, re.IGNORECASE), r) for p, r in PHRASES]

WORDS = {
    "mera": "my", "meri": "my", "mere": "my", "mujhe": "I", "apna": "my", "apni": "my",
    "naya": "new", "naye": "new", "nayi": "new", "purana": "old", "purane": "old", "purani": "old",
    "bahut": "very", "bohot": "very", "bht": "very", "bahot": "very", "poori": "completely", "puri": "completely",
    "pura": "completely", "poora": "completely", "sirf": "only", "jab": "when", "aur": "and", "lekin": "but",
    "magar": "but", "bhi": "also", "phir": "again", "kyun": "why", "kyon": "why", "kya": "what", "abhi": "now",
    "subah": "in the morning", "kal": "yesterday", "raat": "at night", "hamesha": "always", "kabhi": "sometimes",
    "theek": "fine", "thik": "fine", "nahi": "not", "nhi": "not", "nahin": "not", "kaali": "black", "kali": "black",
    "safed": "white", "jagah": "area", "slow": "slow", "kaise": "how", "kese": "how", "waqt": "time", "andar": "inside",
    "bahar": "outside",
}
DROP = {"ki", "ka", "ke", "hai", "hain", "he", "h", "ho", "hota", "hoti", "pe", "par", "mein", "me", "se", "toh",
        "wala", "wali", "wale", "jata", "jati", "jaata", "jaati", "jate", "gaya", "gayi", "gya", "gyi", "raha", "rahi",
        "rahe", "rha", "rhi", "karta", "karti", "karte", "kar", "karke", "hi", "ab", "lagta", "lagti", "pa"}

TRANSLATE_SYSTEM = ("Translate the user's phone or tablet complaint into plain English. Keep device names and English "
                    "technical words as they are. Do not add advice. Reply only with JSON {\"english\": \"...\"}.")
TRANSLATE_SCHEMA = {"type": "OBJECT", "properties": {"english": {"type": "STRING"}}, "required": ["english"]}


def detect(text: str) -> str:
    """'hindi' (Devanagari), 'hinglish' (romanised Hindi mixed with English) or 'english'."""
    if DEVANAGARI_RE.search(text or ""):
        return "hindi"
    words = WORD_RE.findall((text or "").lower())
    strong = sum(w in STRONG for w in words)
    weak = sum(w in WEAK for w in words)
    return "hinglish" if strong >= 2 or (strong == 1 and weak >= 2) else "english"


def hinglish_to_english(text: str) -> str:
    s = " " + text.lower() + " "
    for rx, rep in PHRASES:
        s = rx.sub(rep, s)
    out = []
    for tok in re.findall(r"[a-z0-9']+|[^\sa-z0-9']", s):
        if tok in DROP:
            continue
        out.append(WORDS.get(tok, tok))
    s = " ".join(out)
    s = re.sub(r"\s+([,.!?])", r"\1", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" ,")
    return (s[:1].upper() + s[1:]) if s else text


def to_english(text: str) -> tuple[str, dict | None]:
    """Returns (english_text, info). info is None for English input, else {detected, english, method}."""
    kind = detect(text)
    if kind == "english":
        return text, None
    if kind == "hinglish":
        en = hinglish_to_english(text)
        return en, {"detected": "hinglish", "english": en, "method": "rules"}
    if llm.enabled():                                  # Devanagari Hindi
        usage = llm.Usage()
        out = llm.call_json(TRANSLATE_SYSTEM, text, TRANSLATE_SCHEMA, usage, max_tokens=200)
        en = str((out or {}).get("english") or "").strip()
        if en and not DEVANAGARI_RE.search(en):
            return en, {"detected": "hindi", "english": en, "method": "llm", "cost_usd": usage.cost_usd}
    reason = "LLM unavailable right now" if llm.enabled() else "needs an LLM key"
    return text, {"detected": "hindi", "english": None, "method": f"none ({reason})"}
