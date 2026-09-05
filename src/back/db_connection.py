import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras
# from dotenv import load_dotenv

import tools

# load_dotenv(Path(__file__).resolve().parents[2] / ".env")

class DBConnection:
    def __init__(
        self,
        host: Optional[str] = None,
        dbname: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.host = host or os.environ.get("PGHOST", "localhost")
        self.dbname = dbname or os.environ.get("PGDATABASE", "itmo_hack")
        self.port = int(port or os.environ.get("PGPORT", "5432"))
        self.user = user or os.environ.get("PGUSER", "postgres")
        self.password = password if password is not None else os.environ.get("PGPASSWORD", "1")
        self.conn = None

    def connect(self):
        if self.conn is None or self.conn.closed:
            self.conn = psycopg2.connect(
                host=self.host,
                dbname=self.dbname,
                port=self.port,
                user=self.user,
                password=self.password,
            )
        return self.conn

    def close(self):
        if self.conn is not None and not self.conn.closed:
            self.conn.close()

    def rollback(self):
        if self.conn is not None and not self.conn.closed:
            self.conn.rollback()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def ensure_schema(self):
        conn = self.connect()
        statements = [
            "ALTER TABLE news ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'Экономика';",
            "ALTER TABLE news ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN NOT NULL DEFAULT FALSE;",
            "ALTER TABLE news ADD COLUMN IF NOT EXISTS in_general BOOLEAN NOT NULL DEFAULT TRUE;",
            "ALTER TABLE news ADD COLUMN IF NOT EXISTS fact_when TEXT;",
            "ALTER TABLE sources ADD COLUMN IF NOT EXISTS category_default TEXT NOT NULL DEFAULT 'Экономика';",
            "ALTER TABLE sources ADD COLUMN IF NOT EXISTS poll_interval TEXT NOT NULL DEFAULT 'Каждые 15 минут';",
            "CREATE INDEX IF NOT EXISTS idx_news_in_general ON news (in_general);",
            "CREATE INDEX IF NOT EXISTS idx_news_is_hidden ON news (is_hidden);",
            """
            CREATE TABLE IF NOT EXISTS entities (
                id                  BIGSERIAL PRIMARY KEY,
                object_id           TEXT NOT NULL UNIQUE,
                object_type         TEXT NOT NULL,
                canonical_title     TEXT NOT NULL DEFAULT '—',
                agency              TEXT NOT NULL DEFAULT '',
                kind                TEXT NOT NULL DEFAULT '',
                ids                 JSONB NOT NULL DEFAULT '{}'::jsonb,
                embedding           DOUBLE PRECISION[],
                events              JSONB NOT NULL DEFAULT '[]'::jsonb,
                publication_links   JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT entities_type_check CHECK (object_type IN ('news_plot', 'npa'))
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_entities_object_type ON entities (object_type);",
            "ALTER TABLE news ADD COLUMN IF NOT EXISTS entity_id BIGINT REFERENCES entities(id);",
            "CREATE INDEX IF NOT EXISTS idx_news_entity_id ON news (entity_id);",
        ]
        with conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)
        conn.commit()

    def get_sources_grouped(self) -> dict:
        conn = self.connect()
        query = """
            SELECT s.id, s.name, s.url, s.url_rss, s.source_type, s.status,
                   s.last_update_dt, s.category_default, s.poll_interval,
                   COUNT(n.id) FILTER (WHERE NOT n.is_hidden) AS news_count
            FROM sources s
            LEFT JOIN news n ON n.source_id = s.id
            GROUP BY s.id
            ORDER BY s.source_type, s.name;
        """
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

        by_group = {}
        for row in rows:
            source_out = self._source_row_to_api(row)
            by_group.setdefault(source_out["group"], []).append(source_out)

        groups = [
            {"name": group_name, "sources": by_group[group_name]}
            for group_name in tools.GROUP_ORDER
            if group_name in by_group
        ]
        for group_name in by_group:
            if group_name not in tools.GROUP_ORDER:
                groups.append({"name": group_name, "sources": by_group[group_name]})

        return {"general_count": self.get_general_count(), "groups": groups}

    def get_sources(self) -> dict:
        """
        Плоский формат {id: {...}} — то, что нужно парсерам (tg/web/npa) для
        обхода источников. Отличается от get_sources_grouped(), который
        отдаёт сгруппированную по типу структуру для API/фронтенда.
        """
        conn = self.connect()
        query = """
            SELECT id, name, url, url_rss, source_type, status, last_update_dt, created_at
            FROM sources;
        """
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

        result = {}
        for row in rows:
            (source_id, name, url, url_rss, source_type, status, last_update_dt, created_at) = row
            result[source_id] = {
                "name": name,
                "url": url,
                "url_rss": url_rss,
                "source_type": source_type,
                "status": status,
                "last_update_dt": last_update_dt,
                "created_at": created_at,
            }
        return result

    # Источники НПА не заведены в seed_sources.sql — раньше npa-парсер писал
    # только в JSON-файл, минуя БД. Регистрируем их лениво здесь, при первом
    # запуске (name уникален — sources_name_unique, повторный вызов безопасен).
    NPA_SOURCES: dict[str, dict[str, str]] = {
        "government.ru": {
            "name": "Правительство РФ (government.ru)",
            "url": "https://government.ru",
        },
        "publication.pravo.gov.ru": {
            "name": "Официальное опубликование правовых актов (pravo.gov.ru)",
            "url": "http://publication.pravo.gov.ru",
        },
        "regulation.gov.ru": {
            "name": "Федеральный портал проектов НПА (regulation.gov.ru)",
            "url": "https://regulation.gov.ru",
        },
        "sozd.duma.gov.ru": {
            "name": "Госдума — СОЗД (sozd.duma.gov.ru)",
            "url": "https://sozd.duma.gov.ru",
        },
    }

    def ensure_npa_sources(self) -> dict[str, int]:
        """Регистрирует источники НПА в sources, если их там ещё нет. Возвращает {domain: source_id}."""
        conn = self.connect()
        result: dict[str, int] = {}
        with conn.cursor() as cur:
            for domain, info in self.NPA_SOURCES.items():
                cur.execute(
                    """
                    INSERT INTO sources (name, url, source_type, status)
                    VALUES (%s, %s, 'Регулятор', 'active')
                    ON CONFLICT (name) DO NOTHING;
                    """,
                    (info["name"], info["url"]),
                )
                cur.execute("SELECT id FROM sources WHERE name = %s;", (info["name"],))
                result[domain] = cur.fetchone()[0]
        conn.commit()
        return result


        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM ("
                        " SELECT DISTINCT COALESCE(entity_id, id) FROM news"
                        " WHERE in_general AND NOT is_hidden"
                        ") t;")
            return cur.fetchone()[0]

    def get_source_by_id(self, source_id: int) -> Optional[dict]:
        conn = self.connect()
        query = """
            SELECT s.id, s.name, s.url, s.url_rss, s.source_type, s.status,
                   s.last_update_dt, s.category_default, s.poll_interval,
                   COUNT(n.id) FILTER (WHERE NOT n.is_hidden) AS news_count
            FROM sources s
            LEFT JOIN news n ON n.source_id = s.id
            WHERE s.id = %s
            GROUP BY s.id;
        """
        with conn.cursor() as cur:
            cur.execute(query, (source_id,))
            row = cur.fetchone()
        return self._source_row_to_api(row) if row else None

    def add_source(self, name, url, group, source_type, category_default, poll_interval) -> dict:
        conn = self.connect()
        resolved_type = tools.type_for_group(group, source_type)
        query = """
            INSERT INTO sources (name, url, url_rss, source_type, status, category_default, poll_interval)
            VALUES (%s, %s, %s, %s, 'active', %s, %s)
            RETURNING id;
        """
        with conn.cursor() as cur:
            cur.execute(query, (name, url, url, resolved_type, category_default, poll_interval))
            new_id = cur.fetchone()[0]
        conn.commit()
        return self.get_source_by_id(new_id)

    def update_source(self, source_id: int, fields: dict) -> Optional[dict]:
        conn = self.connect()

        if fields.get("action") == "toggle":
            current = self.get_source_by_id(source_id)
            if current is None:
                return None
            new_status_api = "Пауза" if current["status"] == "Активен" else "Активен"
            fields = dict(fields)
            fields["status"] = new_status_api

        db_fields = {
            "name": fields.get("name"),
            "url": fields.get("url"),
            "status": tools.status_to_db(fields.get("status")) if fields.get("status") else None,
            "category_default": fields.get("category_default"),
            "poll_interval": fields.get("poll_interval"),
        }

        built = tools.build_update_query(
            "sources", "id", source_id, db_fields,
            allowed=("name", "url", "status", "category_default", "poll_interval"),
            returning="id",
        )
        if built is None:
            return self.get_source_by_id(source_id)

        query, params = built
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
        conn.commit()
        if row is None:
            return None
        return self.get_source_by_id(row[0])

    def remove_source(self, source_id: int) -> bool:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM news WHERE source_id = %s;", (source_id,))
            cur.execute("DELETE FROM sources WHERE id = %s;", (source_id,))
            deleted = cur.rowcount
        conn.commit()
        return deleted > 0

    def update_source_last_update(self, source_id, dt: Optional[datetime] = None):
        conn = self.connect()
        dt = dt or datetime.utcnow()
        with conn.cursor() as cur:
            cur.execute("UPDATE sources SET last_update_dt = %s WHERE id = %s;", (dt, source_id))
        conn.commit()

    @staticmethod
    def _source_row_to_api(row) -> dict:
        (
            source_id, name, url, url_rss, source_type, status,
            last_update_dt, category_default, poll_interval, news_count,
        ) = row
        return {
            "id": str(source_id),
            "name": name,
            "group": tools.group_for_type(source_type),
            "type": source_type,
            "url": url_rss or url or "",
            "status": tools.status_to_api(status),
            "last_fetch": tools.humanize_dt(last_update_dt),
            "category_default": category_default,
            "poll_interval": poll_interval,
            "count": news_count or 0,
        }

    _NEWS_SELECT = """
        SELECT n.id, n.source_id, n.source, n.title, n.url, n.author,
               n.category, n.priority, n.description, n.lifetime, n.created_at,
               n.company_mentions, n.regulatory_changes, n.fact_when, n.consequences,
               n.tags, n.in_general, n.is_hidden, n.text,
               s.name AS source_display_name,
               e.object_id, e.object_type, e.events AS entity_events,
               CASE
                 WHEN n.entity_id IS NULL THEN 1
                 ELSE (
                   SELECT COUNT(*)::int FROM news nx
                   WHERE nx.entity_id = n.entity_id AND NOT nx.is_hidden
                 )
               END AS plot_count
        FROM news n
        LEFT JOIN sources s ON s.id = n.source_id
        LEFT JOIN entities e ON e.id = n.entity_id
    """

    def get_news_general(self) -> list:
        conn = self.connect()
        inner = self._NEWS_SELECT.replace(
            "SELECT n.id,",
            "SELECT DISTINCT ON (COALESCE(n.entity_id, n.id)) n.id,",
            1,
        )
        query = inner + """
            WHERE n.in_general AND NOT n.is_hidden
            ORDER BY COALESCE(n.entity_id, n.id),
                     (COALESCE(n.description, '') = '') ASC,
                     COALESCE(n.lifetime, n.created_at) DESC;
        """
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
        rows.sort(key=lambda r: str(r[9] or r[10] or ""), reverse=True)
        return [self._news_row_to_api(row) for row in rows]

    def get_news_manual(self) -> list:
        conn = self.connect()
        query = self._NEWS_SELECT + """
            WHERE n.source_id IS NULL AND NOT n.is_hidden
            ORDER BY COALESCE(n.lifetime, n.created_at) DESC;
        """
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
        return [self._news_row_to_api(row) for row in rows]

    def get_news_by_source(self, source_id: int) -> Optional[list]:
        if self.get_source_by_id(source_id) is None:
            return None
        conn = self.connect()
        query = self._NEWS_SELECT + """
            WHERE n.source_id = %s AND NOT n.is_hidden
            ORDER BY COALESCE(n.lifetime, n.created_at) DESC;
        """
        with conn.cursor() as cur:
            cur.execute(query, (source_id,))
            rows = cur.fetchall()
        return [self._news_row_to_api(row) for row in rows]

    def get_news_by_id(self, news_id: int) -> Optional[dict]:
        conn = self.connect()
        query = self._NEWS_SELECT + " WHERE n.id = %s;"
        with conn.cursor() as cur:
            cur.execute(query, (news_id,))
            row = cur.fetchone()
        return self._news_row_to_api(row) if row else None

    def get_existing_urls(self, source_id) -> set:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute("SELECT url FROM news WHERE source_id = %s;", (source_id,))
            return {row[0] for row in cur.fetchall()}

    def add_parsed_news(
        self,
        source_id: int,
        source: str,
        title: Optional[str],
        url: str,
        author: Optional[str],
        category: Optional[str],
        text: Optional[str],
        priority: Optional[str] = None,
        relevance_score: Optional[float] = None,
    ) -> int:
        """
        Вставка от парсеров (tg/web/npa) — простая позиционная сигнатура,
        которой они уже пользовались раньше через свои локальные
        db_connection.py. Отдельно от add_news(payload) ниже: тот — под API
        (ручное добавление новости из UI), другой формат данных.
        """
        conn = self.connect()
        query = """
            INSERT INTO news (
                source_id, source, title, url, author, category, text,
                priority, relevance_score
            )
            VALUES (
                %s, %s, COALESCE(%s, 'Без заголовка'), %s, %s, COALESCE(%s, 'Экономика'), %s,
                COALESCE(%s::news_priority_enum, 'low'::news_priority_enum), %s
            )
            RETURNING id;
        """
        with conn.cursor() as cur:
            cur.execute(
                query,
                (source_id, source, title, url, author, category, text, priority, relevance_score),
            )
            new_id: int = cur.fetchone()[0]
        conn.commit()
        return new_id

    def add_news(self, payload: dict) -> dict:
        conn = self.connect()

        raw_source = (payload.get("source") or "manual").strip()
        source_id = None
        source_text = "Ручной ввод"
        if raw_source not in ("manual", "", "general"):
            source_id = int(raw_source)
            source_row = self.get_source_by_id(source_id)
            if source_row is None:
                raise ValueError(f"Источник с id={raw_source} не найден")
            source_text = source_row["name"]

        added_manually = source_id is None
        author = payload.get("author") or (payload.get("added_by") if added_manually else None) or (
            "Пользователь" if added_manually else "system"
        )

        link = (payload.get("link") or "").strip() or tools.unique_placeholder_url()
        pub_dt = self._parse_pub_date(payload.get("pub_date"))

        query = """
            INSERT INTO news (
                title, text, source, url, description, lifetime,
                company_mentions, regulatory_changes, fact_when, consequences,
                priority, tags, author, source_id, category, in_general
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """
        params = (
            payload.get("title"),
            payload.get("description") or "",
            source_text,
            link,
            payload.get("description") or "",
            pub_dt,
            tools.to_jsonb(payload.get("who")),
            tools.to_jsonb(payload.get("what")),
            payload.get("when"),
            tools.to_jsonb(payload.get("consequences")),
            tools.priority_to_db(payload.get("importance")),
            payload.get("tags") or [],
            author,
            source_id,
            payload.get("category") or "Экономика",
            bool(payload.get("in_general", True)),
        )
        with conn.cursor() as cur:
            cur.execute(query, params)
            new_id = cur.fetchone()[0]
        conn.commit()
        return self.get_news_by_id(new_id)

    def update_news(self, news_id: int, fields: dict) -> Optional[dict]:
        conn = self.connect()

        db_fields = {
            "title": fields.get("title"),
            "description": fields.get("description"),
            "category": fields.get("category"),
            "url": fields.get("link"),
            "tags": fields.get("tags"),
            "in_general": fields.get("in_general"),
            "is_hidden": fields.get("hidden"),
            "fact_when": fields.get("when"),
        }
        if fields.get("importance"):
            db_fields["priority"] = tools.priority_to_db(fields.get("importance"))
        if fields.get("who") is not None:
            db_fields["company_mentions"] = tools.to_jsonb(fields.get("who"))
        if fields.get("what") is not None:
            db_fields["regulatory_changes"] = tools.to_jsonb(fields.get("what"))
        if fields.get("consequences") is not None:
            db_fields["consequences"] = tools.to_jsonb(fields.get("consequences"))

        allowed = (
            "title", "description", "category", "url", "tags", "in_general",
            "is_hidden", "fact_when", "priority", "company_mentions",
            "regulatory_changes", "consequences",
        )
        built = tools.build_update_query("news", "id", news_id, db_fields, allowed=allowed, returning="id")
        if built is None:
            return self.get_news_by_id(news_id)

        query, params = built
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
        conn.commit()
        if row is None:
            return None
        return self.get_news_by_id(row[0])

    def remove_news(self, news_id: int) -> bool:
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM news WHERE id = %s;", (news_id,))
            deleted = cur.rowcount
        conn.commit()
        return deleted > 0

    @staticmethod
    def _parse_pub_date(value) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _lifecycle_to_api(raw) -> list:
        if not raw:
            return []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                return []
        out = []
        for ev in raw or []:
            if not isinstance(ev, dict):
                continue
            title = (ev.get("title") or ev.get("stage") or "").strip()
            if not title:
                continue
            out.append(
                {
                    "date": ev.get("date") or "",
                    "title": title,
                    "event_type": ev.get("event_type") or ev.get("stage") or "",
                    "stage": ev.get("stage") or "",
                    "link": ev.get("link") or "",
                    "source": ev.get("source") or "",
                }
            )
        dated = [x for x in out if x.get("date")]
        empty = [x for x in out if not x.get("date")]
        dated.sort(key=lambda item: item.get("date") or "")
        return dated + empty

    @staticmethod
    def _news_row_to_api(row) -> dict:
        (
            news_id, source_id, source_text, title, url, author,
            category, priority, description, lifetime, created_at,
            company_mentions, regulatory_changes, fact_when, consequences,
            tags, in_general, is_hidden, text, source_display_name,
            object_id, object_type, entity_events, plot_count,
        ) = row

        added_manually = source_id is None
        source_name = "Ручной ввод" if added_manually else (source_display_name or source_text or "—")
        extra_sources = int(plot_count or 1)

        return {
            "id": str(news_id),
            "source": "manual" if added_manually else str(source_id),
            "source_name": source_name,
            "title": title,
            "link": url or "",
            "author": author or "—",
            "category": category,
            "importance": tools.priority_to_api(priority),
            "description": description or "",
            "pub_date": tools.humanize_dt(lifetime or created_at),
            "paragraphs": tools.count_paragraphs(text),
            "who": tools.from_jsonb(company_mentions),
            "what": tools.from_jsonb(regulatory_changes),
            "when": fact_when,
            "consequences": tools.from_jsonb(consequences),
            "tags": list(tags) if tags else [],
            "in_general": bool(in_general),
            "added_manually": added_manually,
            "added_by": author if added_manually else None,
            "mention_source": None if added_manually else source_name,
            "hidden": bool(is_hidden),
            "entity_id": object_id,
            "object_type": object_type,
            "plot_count": extra_sources,
            "lifecycle": DBConnection._lifecycle_to_api(entity_events),
        }
