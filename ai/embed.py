import hashlib
import math
import os
import sys
import time
from typing import Optional

import requests

from ai.openrouter import OpenRouterError, get_api_key

EMBED_URL = "https://openrouter.ai/api/v1/embeddings"
DEFAULT_EMBED_MODEL = "openai/text-embedding-3-small"
HASH_DIM = 256

def hashed_embed(text: str, *, dim: int = HASH_DIM, n: int = 3) -> list[float]:
    """Стабильный hashed-ngram вектор. Не зависит от PYTHONHASHSEED."""
    vec = [0.0] * dim
    blob = " ".join((text or "").lower().split())
    if len(blob) < n:
        blob = (blob + " " * n)[:n]
    for i in range(len(blob) - n + 1):
        gram = blob[i : i + n].encode("utf-8")
        h = int(hashlib.md5(gram).hexdigest(), 16)
        vec[h % dim] += 1.0
    return _l2(vec)

def _l2(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]

def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))

def embed_texts(
    texts: list[str],
    *,
    model: Optional[str] = None,
) -> tuple[list[list[float]], str]:
    """Возвращает (векторы, метод: openrouter|hashed)."""
    if not texts:
        return [], "empty"
    model = model or os.environ.get("EMBEDDING_MODEL", DEFAULT_EMBED_MODEL)
    last_err: Optional[Exception] = None
    for attempt in range(3):
        try:
            key = get_api_key()
            resp = requests.post(
                EMBED_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={"model": model, "input": texts},
                timeout=60,
            )
            if resp.status_code >= 400:
                raise OpenRouterError(
                    f"embed HTTP {resp.status_code}: {resp.text[:300]}",
                    fatal=resp.status_code in (401, 402),
                )
            data = resp.json()
            items = sorted(data.get("data") or [], key=lambda x: x.get("index", 0))
            vectors = [it.get("embedding") or [] for it in items]
            if len(vectors) != len(texts) or not vectors[0]:
                raise OpenRouterError("embed: empty or mismatched vectors")
            return vectors, f"openrouter:{model}"
        except OpenRouterError as exc:
            if getattr(exc, "fatal", False):
                raise
            last_err = exc
            break
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            last_err = exc
            time.sleep(1.5 * (attempt + 1))
    print(f"embed fallback hashed: {last_err}", file=sys.stderr)
    return [hashed_embed(t) for t in texts], "hashed"
