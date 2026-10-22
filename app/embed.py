"""Local CPU sentence embeddings (fastembed / ONNX). Vectors are L2-normalised, so dot = cosine."""
import os
import threading

import numpy as np

from . import config

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from fastembed import TextEmbedding
                # EMBED_THREADS caps the CPU threads one embedding call may use, so parallel requests don't fight
                # over every core (2 measured best on 16 cores: eval/runs/scale.md); 0 = the library default (all cores)
                threads = int(os.getenv("EMBED_THREADS", "2")) or None
                _model = TextEmbedding(config.EMBED_MODEL, cache_dir=str(config.MODEL_CACHE), threads=threads)
    return _model


def embed(texts: list[str], batch_size: int = 64) -> np.ndarray:
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    vecs = np.array(list(_get_model().embed(texts, batch_size=batch_size)), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / np.maximum(norms, 1e-9)


def embed_one(text: str) -> np.ndarray:
    return embed([text])[0]


def warmup() -> None:
    embed(["warm up"])
