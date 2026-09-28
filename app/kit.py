"""Loads the starter kit: official schema, deeplink catalog, SIIS rows and input queries."""
import importlib.util
import json
from functools import lru_cache

from rapidfuzz import fuzz

from . import config


@lru_cache(maxsize=1)
def schema():
    """The official schema.py, imported unchanged from the kit."""
    spec = importlib.util.spec_from_file_location("kit_schema", config.SCHEMA_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@lru_cache(maxsize=1)
def deeplinks() -> list[dict]:
    with open(config.DEEPLINKS_PATH, encoding="utf-8") as f:
        return json.load(f)["deeplinks"]


@lru_cache(maxsize=1)
def siis_rows() -> list[dict]:
    with open(config.SIIS_PATH, encoding="utf-8") as f:
        return json.load(f)["responses"]


def input_queries() -> list[str]:
    with open(config.INPUT_PATH, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def match_siis(query: str) -> dict | None:
    """Finds the SIIS row whose original_query best matches an input line (texts differ slightly)."""
    best, best_score = None, 0.0
    for row in siis_rows():
        score = fuzz.ratio(query.lower(), row["original_query"].lower())
        if score > best_score:
            best, best_score = row, score
    return best if best_score >= 80 else None
