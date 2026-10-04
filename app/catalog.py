"""Settings Feature Graph + hybrid (BM25 + dense) deeplink resolver.

Matching uses only descriptive fields (feature key, message, description, qna_description) and the
operation type; the masked URI is never searched. Chosen entries are copied verbatim into the plan.
"""
import hashlib
import json
import re
from dataclasses import dataclass, field

import numpy as np
from rank_bm25 import BM25Okapi

from . import config, embed, kit
from .text import tokens

APPLIANCE_RE = re.compile(r"(?i)refrigerator|fridge|air conditioner|washer|washing machine|dryer|oven|dishwasher|robot vacuum|air purifier|\bTV\b")
OP_BY_TYPE = {"onURL": "on", "offURL": "off", "onClickURL": "view", "updateURL": "update"}
# on-screen button names that the kit articles use for a catalog action whose message words differ
TARGET_ALIASES = {"optimize now": "Optimize device performance", "optimise now": "Optimize device performance"}
VERB_RE = re.compile(r"^(view|enable|disable|adjust|check|increase|decrease|set|open|switch|diagnose|optimize)\s+", re.I)


@dataclass
class Entry:
    id: str
    raw: dict
    feature: str
    op: str
    appliance: bool
    feature_tokens: set = field(default_factory=set)

    @property
    def search_text(self) -> str:
        r = self.raw
        return f"{self.feature}. {r.get('message', '')}. {r.get('description', '')} {r.get('qna_description') or ''}"


@dataclass
class Match:
    entry: Entry | None
    score: float
    dense: float
    coverage: float
    accepted: bool
    candidates: list


def _feature_of(raw: dict) -> str:
    key = (raw.get("validation") or {}).get("key")
    if key and len(key) > 2:
        return key
    msg = VERB_RE.sub("", raw.get("message", "")).strip()
    if msg and msg.lower() not in {"onurl", "offurl", "check current setting"}:
        return msg
    m = re.search(r"(?:Opens|Enables|Disables|Updates|Retrieves|Checks) (?:the )?(.+?)(?: settings| page| via|\.)", raw.get("description", ""))
    return m.group(1) if m else raw.get("description", "")[:40]


def _op_of(raw: dict) -> str:
    t = raw.get("originalType")
    if t in OP_BY_TYPE:
        return OP_BY_TYPE[t]
    msg = (raw.get("message") or "").lower()
    if msg.startswith("onurl"):
        return "on"
    if msg.startswith("offurl"):
        return "off"
    return "view"


class Catalog:
    def __init__(self) -> None:
        self.entries: list[Entry] = []
        self.dummy: dict | None = None
        for raw in kit.deeplinks():
            if raw.get("id") == "DL-DUMMY" or str(raw.get("deeplink", "")).endswith("://dummy_positive"):
                self.dummy = raw
                continue
            feat = _feature_of(raw)
            e = Entry(raw["id"], raw, feat, _op_of(raw), bool(APPLIANCE_RE.search(raw.get("description", "") + " " + raw.get("message", ""))))
            e.feature_tokens = set(tokens(feat))
            self.entries.append(e)
        self.searchable = [e for e in self.entries if not e.appliance]
        self.dummy_uri = self.dummy["deeplink"] if self.dummy else config.DUMMY_DEEPLINK
        self.valid_uris = {e.raw["deeplink"] for e in self.entries} | {self.dummy_uri}
        self.by_uri = {e.raw["deeplink"]: e for e in self.entries}
        self._bm25 = BM25Okapi([tokens(e.feature + " " + e.feature + " " + e.search_text) or ["_"] for e in self.searchable])
        self._emb = self._load_or_build_embeddings()

    # ---------- dense index (cached on disk, rebuilt if the catalog changes) ----------
    def _load_or_build_embeddings(self) -> np.ndarray:
        texts = [e.search_text for e in self.searchable]
        digest = hashlib.sha256(("\n".join(texts) + config.EMBED_MODEL).encode()).hexdigest()[:16]
        path = config.DERIVED_DIR / f"catalog_emb_{digest}.npy"
        if path.exists():
            return np.load(path)
        vecs = embed.embed(texts)
        config.DERIVED_DIR.mkdir(parents=True, exist_ok=True)
        np.save(path, vecs)
        return vecs

    def feature_graph(self) -> dict:
        """Groups entries that control the same feature (e.g. on/off twins sharing a validation key)."""
        graph: dict[str, list] = {}
        for e in self.entries:
            graph.setdefault(e.feature, []).append({"id": e.id, "op": e.op, "message": e.raw.get("message"), "appliance": e.appliance})
        return graph

    # ---------- resolver ----------
    def match(self, target: str, op_hint: str | None = None, context: str = "") -> Match:
        """Finds the catalog entry for an action whose most specific screen/feature is `target`.

        Depth-aware: lexical coverage is measured against the target (last path element), so a parent
        menu mentioned only in `context` cannot win. Action-aware: on/off hints must agree with the entry.
        """
        target = TARGET_ALIASES.get(target.lower().strip(" ."), target)
        q_tokens = set(tokens(target))
        if not q_tokens:
            return Match(None, 0.0, 0.0, 0.0, False, [])
        bm = self._bm25.get_scores(list(q_tokens) + tokens(context))
        qv = embed.embed_one(f"{target}. {context}".strip())
        dense = self._emb @ qv
        rank_b = {i: r for r, i in enumerate(np.argsort(-bm))}
        rank_d = {i: r for r, i in enumerate(np.argsort(-dense))}
        pool = set(np.argsort(-bm)[:25]) | set(np.argsort(-dense)[:25])
        scored = []
        for i in pool:
            e = self.searchable[i]
            ft = e.feature_tokens or set(tokens(e.raw.get("message", "")))
            coverage = len(ft & q_tokens) / max(len(ft), 1)
            precision = len(ft & q_tokens) / max(len(q_tokens), 1)
            op_bonus = 0.0
            mismatch = False
            if op_hint in ("on", "off"):
                if e.op in ("on", "off"):
                    mismatch = e.op != op_hint
                    op_bonus = -0.5 if mismatch else 0.2
                else:
                    op_bonus = 0.05
            elif op_hint == "view":
                op_bonus = 0.15 if e.op == "view" else -0.05
            elif op_hint == "update":
                op_bonus = 0.15 if e.op == "update" else 0.0
            rrf = 1 / (60 + rank_b[i]) + 1 / (60 + rank_d[i])
            feat_l, tgt_l = e.feature.lower(), target.lower().strip()
            phrase_bonus = 0.3 if feat_l and (feat_l in tgt_l or tgt_l in feat_l) else 0.0   # exact phrase evidence
            score = 10 * rrf + 0.6 * coverage + 0.2 * precision + 0.4 * float(dense[i]) + op_bonus + phrase_bonus
            scored.append((score, e, float(dense[i]), coverage, mismatch))
        scored.sort(key=lambda t: (-t[0], t[1].id))
        best = scored[0]
        # word order matters: "Screen lock" (security) is not "Lock screen" (notifications) although the tokens match
        feat, tgt = best[1].feature.lower(), target.lower().strip()
        phrase_ok = feat in tgt or tgt in feat
        lexical_ok = best[3] >= config.MAP_MIN_COVERAGE and best[2] >= 0.6 and (phrase_ok or best[2] >= 0.85)
        accepted = (not best[4]) and (lexical_ok or best[2] >= max(config.MAP_MIN_DENSE, 0.85 if not phrase_ok else 0.0))
        cands = [{"id": s[1].id, "message": s[1].raw.get("message"), "score": round(s[0], 3), "dense": round(s[2], 3), "coverage": round(s[3], 2)} for s in scored[:5]]
        return Match(best[1], best[0], best[2], best[3], accepted, cands)

    @staticmethod
    def actionable(e: Entry) -> dict:
        r = e.raw
        return {"deeplink": r["deeplink"], "description": r.get("description", ""), "message": r.get("message", ""), "originalType": r.get("originalType")}

    @staticmethod
    def validation(e: Entry) -> dict | None:
        v = e.raw.get("validation")
        if not v or not v.get("deeplink") or not v.get("key"):
            return None
        return {"deeplink": v["deeplink"], "key": v["key"], "resultType": v.get("resultType"), "condition": v.get("condition"), "value": v.get("value")}


_catalog: Catalog | None = None


def get() -> Catalog:
    global _catalog
    if _catalog is None:
        _catalog = Catalog()
    return _catalog


if __name__ == "__main__":
    c = get()
    print(len(c.entries), "entries,", len(c.searchable), "searchable")
    for t, op in [("Touch sensitivity", "on"), ("Navigation bar", "view"), ("Adaptive brightness", "on"), ("Power saving", "on"), ("Screen timeout", "view")]:
        m = c.match(t, op)
        print(t, op, "->", m.entry.id, m.entry.raw["message"], m.accepted, json.dumps(m.candidates[:2]))
