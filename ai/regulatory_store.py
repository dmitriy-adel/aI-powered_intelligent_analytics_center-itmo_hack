import json
import re
import uuid
from pathlib import Path
from typing import Any, Optional

from ai.embed import cosine

STRONG_ID_KEYS = ("sozd_bill", "regulation_project", "regulation_npa_id", "pravo_eo")
WEAK_ID_KEYS = ("pp_number", "fz_number")
ALL_ID_KEYS = STRONG_ID_KEYS + WEAK_ID_KEYS

BILL_RE = re.compile(r"\b(\d{6,7}-\d)\b")
REG_URL_RE = re.compile(r"regulation\.gov\.ru/projects/(\d+)", re.I)
REG_NPA_RE = re.compile(r"\b(\d{2}/\d{2}/\d{2}-\d{2}/\d{8,})\b")
PRAVO_RE = re.compile(r"(0001\d{12})")
PP_RE = re.compile(r"(?:ПП|постановлен\w+\s+Правительства)[^\d]{0,15}№\s*(\d+)", re.I)
FZ_RE = re.compile(r"(?:ФЗ|федеральн\w+\s+закон)[^\d]{0,12}№\s*([\d\-]+)", re.I)

def empty_ids() -> dict[str, str]:
    return {k: "" for k in ALL_ID_KEYS}

def _clean_id(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()

def merge_ids(*dicts: dict) -> dict[str, str]:
    out = empty_ids()
    for d in dicts:
        if not d:
            continue
        for key in ALL_ID_KEYS:
            val = _clean_id(d.get(key))
            if val and not out[key]:
                out[key] = val
    return out

def ids_from_article(article: dict) -> dict[str, str]:
    """ID из парсера источника + regex по URL/тексту (даже до LLM)."""
    found = empty_ids()
    oid = _clean_id(article.get("official_id"))
    id_type = (article.get("id_type") or "").strip()
    link = article.get("link") or ""
    if oid:
        if id_type == "sozd_bill" or BILL_RE.fullmatch(oid):
            found["sozd_bill"] = oid
        elif id_type == "regulation_project" or (
            oid.isdigit() and "regulation.gov.ru" in link
        ):
            found["regulation_project"] = oid
        elif id_type == "pravo_eo" or oid.startswith("0001"):
            found["pravo_eo"] = oid
        extra = (article.get("extra") or {}).get("project_id")
        if extra:
            found["regulation_npa_id"] = str(extra)

    blob = " ".join(
        [
            article.get("link") or "",
            article.get("title") or "",
            article.get("text") or "",
            article.get("description") or "",
        ]
    )
    if m := BILL_RE.search(blob):
        found["sozd_bill"] = found["sozd_bill"] or m.group(1)
    if m := REG_URL_RE.search(blob):
        found["regulation_project"] = found["regulation_project"] or m.group(1)
    if m := REG_NPA_RE.search(blob):
        found["regulation_npa_id"] = found["regulation_npa_id"] or m.group(1)
    if m := PRAVO_RE.search(blob):
        found["pravo_eo"] = found["pravo_eo"] or m.group(1)
    if m := PP_RE.search(blob):
        found["pp_number"] = found["pp_number"] or m.group(1)
    if m := FZ_RE.search(blob):
        found["fz_number"] = found["fz_number"] or m.group(1)
    related = (article.get("extra") or {}).get("related_ids") or {}
    if related.get("sozd_bills"):
        found["sozd_bill"] = found["sozd_bill"] or related["sozd_bills"][0]
    return found

def has_strong_id(ids: dict) -> bool:
    return any(_clean_id(ids.get(k)) for k in STRONG_ID_KEYS)

def _event_key(event: dict) -> tuple:
    return (
        (event or {}).get("date") or "",
        (event or {}).get("title") or "",
        (event or {}).get("link") or "",
        (event or {}).get("event_type") or "",
    )

def _append_event(obj: dict, event: dict) -> None:
    if not event:
        return
    events = obj.setdefault("events", [])
    keys = {_event_key(e) for e in events}
    if _event_key(event) in keys:
        return
    events.append(event)
    link = event.get("link")
    if link:
        obj.setdefault("publication_links", [])
        if link not in obj["publication_links"]:
            obj["publication_links"].append(link)

class RegulatoryStore:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = {"objects": []}
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))
            self.data.setdefault("objects", [])

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @property
    def objects(self) -> list[dict]:
        return self.data["objects"]

    def find_by_ids(self, ids: dict) -> Optional[dict]:
        """Точный match по сильным ID; слабые — только если уникальны в сторе."""
        for key in STRONG_ID_KEYS:
            val = _clean_id(ids.get(key))
            if not val:
                continue
            hits = [o for o in self.objects if _clean_id((o.get("ids") or {}).get(key)) == val]
            if hits:
                return hits[0]
        for key in WEAK_ID_KEYS:
            val = _clean_id(ids.get(key))
            if not val:
                continue
            hits = [o for o in self.objects if _clean_id((o.get("ids") or {}).get(key)) == val]
            if len(hits) == 1:
                return hits[0]
        return None

    def knn(self, vector: list[float], *, k: int = 5, object_type: str = "npa") -> list[tuple[dict, float]]:
        scored: list[tuple[dict, float]] = []
        for obj in self.objects:
            if obj.get("object_type", "npa") != object_type:
                continue
            emb = obj.get("embedding") or []
            if not emb:
                continue
            scored.append((obj, cosine(vector, emb)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def create(
        self,
        *,
        extract: dict,
        ids: dict,
        embedding: list[float],
        event: dict,
        object_type: str = "npa",
        extra_events: Optional[list] = None,
    ) -> dict:
        obj = {
            "object_id": _new_object_id(ids, object_type),
            "object_type": object_type,
            "canonical_title": extract.get("title") or event.get("title") or "—",
            "agency": extract.get("agency") or "",
            "kind": extract.get("kind") or "",
            "ids": merge_ids(ids),
            "embedding": embedding,
            "events": [],
            "publication_links": [],
        }
        _append_event(obj, event)
        for ev in extra_events or []:
            _append_event(obj, ev)
        self.objects.append(obj)
        return obj

    def attach(self, obj: dict, *, ids: dict, event: dict, embedding: Optional[list[float]] = None) -> dict:
        obj["ids"] = merge_ids(obj.get("ids") or {}, ids)
        _append_event(obj, event)
        if embedding and not obj.get("embedding"):
            obj["embedding"] = embedding
        if extract_title := event.get("object_title"):
            if not obj.get("canonical_title"):
                obj["canonical_title"] = extract_title
        return obj

def _new_object_id(ids: dict, object_type: str) -> str:
    for key in STRONG_ID_KEYS:
        val = _clean_id(ids.get(key))
        if val:
            safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", val)
            return f"{object_type}_{key}_{safe}"
    return f"{object_type}_{uuid.uuid4().hex[:10]}"

def canonical_embed_text(extract: dict, ids: dict, extra: str = "") -> str:
    parts = [
        extract.get("title") or "",
        extract.get("agency") or "",
        extract.get("kind") or "",
        extract.get("description") or "",
        extra or "",
    ]
    for key, val in (ids or {}).items():
        if val:
            parts.append(f"{key}:{val}")
    return " ".join(part for part in parts if part)
