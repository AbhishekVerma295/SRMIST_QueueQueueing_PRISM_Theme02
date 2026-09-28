import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# tests never touch the shipped, pre-warmed cache
(ROOT / ".tmp").mkdir(exist_ok=True)
os.environ["CACHE_DB"] = str(ROOT / ".tmp" / "test_cache.sqlite")
test_db = ROOT / ".tmp" / "test_cache.sqlite"
if test_db.exists():
    test_db.unlink()
