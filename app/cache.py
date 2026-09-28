"""Fast-path semantic cache (Stage 3).

L1 exact: normalised query text (+ SIIS hash when a reference text is sent).
L1 semantic: embedding of the incoming query vs every stored key (original query, canonical query and
its 8-10 variations), accepted only if
  * cosine >= CACHE_MIN_SIM,
  * the symptom guard agrees (a query naming a symptom can't hit an entry about another symptom),
  * the SIIS hash matches when a reference text is supplied,
  * the entry's trust tier is validated/auto (provisional plans are never reused for paraphrases).
No LLM is involved, so hits cost $0 and stay far below the 300 ms budget.
"""
import hashlib
import json
import sqlite3
import threading
import time

import numpy as np

from . import config, embed
from .enrich_rules import symptoms_of
from .text import normalize

REUSABLE_TIERS = ("validated", "auto")


def norm_key(text: str) -> str:
    return normalize(text).lower().strip(" .!?\"'")


def siis_hash(siis_text: str | None) -> str | None:
    return hashlib.sha256(normalize(siis_text).encode()).hexdigest()[:16] if siis_text else None


class SemanticCache:
    def __init__(self, path=config.CACHE_DB) -> None:
        self.path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.executescript(
            """CREATE TABLE IF NOT EXISTS entries(
                   id INTEGER PRIMARY KEY, norm_query TEXT, siis_hash TEXT, symptoms TEXT,
                   envelope TEXT, tier TEXT, created REAL);
               CREATE TABLE IF NOT EXISTS keys(entry_id INTEGER, text TEXT, vec BLOB);"""
        )
        self._load()

    def _load(self) -> None:
        rows = self.db.execute("SELECT id, norm_query, siis_hash, symptoms, envelope, tier FROM entries").fetchall()
        self.entries = {r[0]: {"norm": r[1], "siis": r[2], "symptoms": set(json.loads(r[3])), "envelope": json.loads(r[4]), "tier": r[5]} for r in rows}
        self.exact = {}
        for eid, e in self.entries.items():
            self.exact.setdefault(e["norm"], []).append(eid)
        keys = self.db.execute("SELECT entry_id, text, vec FROM keys").fetchall()
        self.key_ids = np.array([k[0] for k in keys], dtype=np.int64)
        self.key_vecs = np.stack([np.frombuffer(k[2], dtype=np.float32) for k in keys]) if keys else np.zeros((0, 384), np.float32)

    def __len__(self) -> int:
        return len(self.entries)

    def _siis_ok(self, entry: dict, s_hash: str | None) -> bool:
        return s_hash is None or entry["siis"] == s_hash

    def lookup(self, query: str, s_hash: str | None) -> tuple[dict | None, str, float]:
        """Returns (envelope, how, similarity); how is 'exact', 'semantic' or 'miss'."""
        nk = norm_key(query)
        for eid in self.exact.get(nk, []):
            e = self.entries[eid]
            if self._siis_ok(e, s_hash):
                return e["envelope"], "exact", 1.0
        if not len(self.key_ids):
            return None, "miss", 0.0
        qv = embed.embed_one(normalize(query))
        sims = self.key_vecs @ qv
        q_symptoms = {s[0] for s in symptoms_of(query)}
        for i in np.argsort(-sims)[:10]:
            sim = float(sims[i])
            if sim < config.CACHE_MIN_SIM:
                break
            e = self.entries[int(self.key_ids[i])]
            if e["tier"] not in REUSABLE_TIERS or not self._siis_ok(e, s_hash):
                continue
            if q_symptoms and e["symptoms"] and not (q_symptoms & e["symptoms"]):
                continue                      # symptom guard: flicker must not hit a cracked-screen plan
            return e["envelope"], "semantic", sim
        return None, "miss", float(sims.max()) if len(sims) else 0.0

    def store(self, query: str, s_hash: str | None, envelope: dict, keys: list[str], symptoms: list[str], tier: str = "auto") -> None:
        texts = list(dict.fromkeys(normalize(k) for k in [query, *keys] if k))
        vecs = embed.embed(texts)
        with self._lock:
            cur = self.db.execute(
                "INSERT INTO entries(norm_query, siis_hash, symptoms, envelope, tier, created) VALUES (?,?,?,?,?,?)",
                (norm_key(query), s_hash, json.dumps(sorted(set(symptoms))), json.dumps(envelope), tier, time.time()),
            )
            eid = cur.lastrowid
            self.db.executemany("INSERT INTO keys(entry_id, text, vec) VALUES (?,?,?)",
                                [(eid, t, v.astype(np.float32).tobytes()) for t, v in zip(texts, vecs)])
            self.db.commit()
            self._load()

    def clear(self) -> None:
        with self._lock:
            self.db.executescript("DELETE FROM entries; DELETE FROM keys;")
            self.db.commit()
            self._load()
