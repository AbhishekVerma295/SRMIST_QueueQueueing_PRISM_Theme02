"""Paths and tunable thresholds. Everything can be overridden with environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

KIT_DIR = Path(os.getenv("KIT_DIR", ROOT / "starter_kit"))
DERIVED_DIR = Path(os.getenv("DERIVED_DIR", ROOT / "data" / "derived"))
MODEL_CACHE = Path(os.getenv("MODEL_CACHE", ROOT / "models_cache"))
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")

DEEPLINKS_PATH = KIT_DIR / "deeplinks.json"
SIIS_PATH = KIT_DIR / "siis_responses.json"
INPUT_PATH = KIT_DIR / "input.txt"
SCHEMA_PATH = KIT_DIR / "schema.py"
CACHE_DB = Path(os.getenv("CACHE_DB", DERIVED_DIR / "cache.sqlite"))

DUMMY_DEEPLINK = "bixby://dummy_positive"

# Deeplink mapping gates
MAP_MIN_COVERAGE = float(os.getenv("MAP_MIN_COVERAGE", "0.75"))  # share of feature tokens found in the step text
MAP_MIN_DENSE = float(os.getenv("MAP_MIN_DENSE", "0.80"))        # cosine needed when lexical coverage is weak

# Relevance of the reference text to the complaint (offline mode)
DOC_MIN_RELEVANCE = float(os.getenv("DOC_MIN_RELEVANCE", "0.69"))

# Semantic cache
CACHE_MIN_SIM = float(os.getenv("CACHE_MIN_SIM", "0.86"))
CACHE_WRITE = os.getenv("CACHE_WRITE", "1") == "1"

MAX_QUERY_CHARS = 2000
MAX_SIIS_CHARS = 30000
