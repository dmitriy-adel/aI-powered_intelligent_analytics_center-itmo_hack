from typing import Any, Optional

import psycopg2.extras

from ai.embed import cosine
from ai.regulatory_store import (
    STRONG_ID_KEYS,
    WEAK_ID_KEYS,
    _append_event,
    _clean_id,
    _new_object_id,
    merge_ids,
)

class PostgresEntityStore:
    def __init__(self, db: Any):
        self.db = db
        self.db.ensure_schema()
        self._cache: Optional[list[dict]] = None

    def save(self) -> None:
        conn = self.db.connect()
        conn.commit()

    @property
    def objects(self) -> list[dict]:
        if self._cache is None:
            self._cache = self._load_all()
        return self._cache

    def _invalidate(self) -> None:
        self._cache = None

    def _load_all(self) -> list[dict]:
        conn = self.db.connect()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, object_id, object_type, canonical_title, agency, kind,
                       ids, embedding, events, publication_links
                FROM entities
                """
            )
            return [self._row_to_obj(row) for row in cur.fetchall()]

    @staticmethod
    def _row_to_obj(row: Any) -> dict:
        emb = row.get("embedding")
        return {
            "db_id": row["id"],
            "object_id": row["object_id"],
            "object_type": row["object_type"],
            "canonical_title": row["canonical_title"],
            "agency": row.get("agency") or "",
            "kind": row.get("kind") or "",
            "ids": row.get("ids") or {},
            "embedding": list(emb) if emb else [],
            "events": row.get("events") or [],
            "publication_links": row.get("publication_links") or [],
        }

    def find_by_ids(self, ids: dict) -> Optional[dict]:
        conn = self.db.connect()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for key in STRONG_ID_KEYS:
                val = _clean_id(ids.get(key))
                if not val:
                    continue
                cur.execute(
                    "SELECT * FROM entities WHERE object_type = 'npa' AND ids->>%s = %s LIMIT 2",
                    (key, val),
                )
                rows = cur.fetchall()
                if rows:
                    return self._row_to_obj(rows[0])
            for key in WEAK_ID_KEYS:
                val = _clean_id(ids.get(key))
                if not val:
                    continue
                cur.execute(
                    "SELECT * FROM entities WHERE object_type = 'npa' AND ids->>%s = %s",
                    (key, val),
                )
                rows = cur.fetchall()
                if len(rows) == 1:
                    return self._row_to_obj(rows[0])
        return None

    def knn(self, vector: list[float], *, k: int = 5, object_type: str = "npa") -> list[tuple[dict, float]]:
        scored: list[tuple[dict, float]] = []
        for obj in self.objects:
            if obj.get("object_type") != object_type:
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
        object_id = _new_object_id(ids, object_type)
        payload = {
            "object_id": object_id,
            "object_type": object_type,
            "canonical_title": extract.get("title") or event.get("title") or "—",
            "agency": extract.get("agency") or "",
            "kind": extract.get("kind") or "",
            "ids": merge_ids(ids),
            "embedding": embedding or None,
            "events": [],
            "publication_links": [],
        }
        _append_event(payload, event)
        for ev in extra_events or []:
            _append_event(payload, ev)
        conn = self.db.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO entities (
                    object_id, object_type, canonical_title, agency, kind,
                    ids, embedding, events, publication_links
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    payload["object_id"],
                    payload["object_type"],
                    payload["canonical_title"],
                    payload["agency"],
                    payload["kind"],
                    psycopg2.extras.Json(payload["ids"]),
                    payload["embedding"],
                    psycopg2.extras.Json(payload["events"]),
                    psycopg2.extras.Json(payload["publication_links"]),
                ),
            )
            db_id = cur.fetchone()[0]
        conn.commit()
        obj = dict(payload)
        obj["db_id"] = db_id
        obj["embedding"] = list(embedding or [])
        self._bind_news(event, db_id)
        self._invalidate()
        return obj

    def attach(self, obj: dict, *, ids: dict, event: dict, embedding: Optional[list[float]] = None) -> dict:
        merged_ids = merge_ids(obj.get("ids") or {}, ids)
        _append_event(obj, event)
        links = list(obj.get("publication_links") or [])
        events = list(obj.get("events") or [])
        title = obj.get("canonical_title") or ""
        if event.get("object_title") and (not title or title == "—"):
            title = event["object_title"]
        emb = obj.get("embedding") or embedding or []
        db_id = obj.get("db_id")
        conn = self.db.connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE entities
                SET ids = %s,
                    events = %s,
                    publication_links = %s,
                    canonical_title = %s,
                    embedding = COALESCE(embedding, %s)
                WHERE id = %s
                """,
                (
                    psycopg2.extras.Json(merged_ids),
                    psycopg2.extras.Json(events),
                    psycopg2.extras.Json(links),
                    title or obj.get("canonical_title") or "—",
                    embedding or None,
                    db_id,
                ),
            )
        conn.commit()
        obj["ids"] = merged_ids
        obj["events"] = events
        obj["publication_links"] = links
        obj["canonical_title"] = title or obj.get("canonical_title")
        if embedding and not obj.get("embedding"):
            obj["embedding"] = embedding
        self._bind_news(event, db_id)
        self._invalidate()
        return obj

    def _bind_news(self, event: dict, entity_db_id: Optional[int]) -> None:
        news_id = event.get("news_id") if event else None
        if not news_id or not entity_db_id:
            return
        conn = self.db.connect()
        with conn.cursor() as cur:
            cur.execute("UPDATE news SET entity_id = %s WHERE id = %s", (entity_db_id, int(news_id)))
        conn.commit()
