import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# tests never touch the shipped, pre-warmed cache
(ROOT / ".tmp").mkdir(exist_ok=True)
os.environ["CACHE_DB"] = str(ROOT / ".tmp" / "test_cache.sqlite")
# hermetic: never call the real LLM from tests (load_dotenv does not override an existing variable);
# the LLM path is covered with a fake LLM in test_llm_path.py
os.environ["LLM_API_KEY"] = ""
test_db = ROOT / ".tmp" / "test_cache.sqlite"
if test_db.exists():
    test_db.unlink()
