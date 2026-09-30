"""Knowledge-base article search (demo/UX helper, outside the Theme 02 contract).

When a user types a new complaint without a reference article, the UI can look up the most relevant
article in the knowledge base (the official kit's SIIS articles) and then call /v1/troubleshoot with it,
so the plan is still grounded in an official article. The /v1/troubleshoot contract itself is unchanged.
"""
from functools import lru_cache

import numpy as np

from . import embed, kit
from .enrich_rules import clean_query, symptoms_of
from .extract_rules import clean_siis


@lru_cache(maxsize=1)
def _index():
    arts, seen = [], set()
    for row in kit.siis_rows():
        s = row["siis_response"]
        if s["content"] in seen:
            continue
        seen.add(s["content"])
        arts.append({"id": row["id"], "title": s["title"], "siis_response": s,
                     "symptoms": {x[0] for x in symptoms_of(s["title"] + " " + clean_siis(s["content"])[:1500])}})
    vecs = embed.embed([f"{a['title']}. {clean_siis(a['siis_response']['content'])[:600]}" for a in arts])
    return arts, vecs


def search(query: str, k: int = 3) -> list[dict]:
    arts, vecs = _index()
    q = clean_query(query)
    sims = vecs @ embed.embed_one(q)
    q_sym = {x[0] for x in symptoms_of(q)}
    out = []
    for i in np.argsort(-sims)[: max(k, 5)]:
        a = arts[int(i)]
        score = float(sims[i]) + (0.08 if q_sym & a["symptoms"] else 0.0)   # symptom agreement bonus
        out.append({"title": a["title"], "score": round(score, 3), "symptom_match": bool(q_sym & a["symptoms"]),
                    "siis_response": a["siis_response"]})
    out.sort(key=lambda r: -r["score"])
    return out[:k]
