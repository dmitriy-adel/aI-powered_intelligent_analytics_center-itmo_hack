import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class DBConnection:
    def __init__(
        self,
        host=None,
        dbname=None,
        port=None,
        user=None,
        password=None,
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

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_sources(self) -> dict:
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

    def update_source_last_update(self, source_id, dt: Optional[datetime] = None):
        """Проставляет last_update_dt источнику после успешного сбора данных."""
        conn = self.connect()
        dt = dt or datetime.utcnow()
        query = "UPDATE sources SET last_update_dt = %s WHERE id = %s;"
        with conn.cursor() as cur:
            cur.execute(query, (dt, source_id))
        conn.commit()

    # ---------- news ----------

    def add_news(self, source_id, source, title, url, author, category, text):
        conn = self.connect()
        query = """
            INSERT INTO news (source_id, source, title, url, author, category, text)
            VALUES (%s, %s, COALESCE(%s, 'Без заголовка'), %s, %s, COALESCE(%s, 'Экономика'), %s)
            RETURNING id;
        """

        with conn.cursor() as cur:
            cur.execute(query, (source_id, source, title, url, author, category, text))
            new_id = cur.fetchone()[0]

        conn.commit()
        return new_id

    def get_news(self) -> dict:
        conn = self.connect()
        query = """
            SELECT id, source_id, source, title, url, author,
                   category, description, created_at
            FROM news;
        """
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

        return self._rows_to_news_dict(rows)

    def get_news_by_id(self, news_id):
        conn = self.connect()
        query = """
            SELECT id, source_id, source, title, url, author,
                   category, description, created_at
            FROM news
            WHERE id = %s;
        """
        with conn.cursor() as cur:
            cur.execute(query, (news_id,))
            row = cur.fetchone()

        if row is None:
            return None

        news_dict = self._rows_to_news_dict([row])
        return news_dict[news_id]

    def get_news_by_source(self, source_id) -> dict:
        conn = self.connect()
        query = """
            SELECT id, source_id, source, title, url, author,
                   category, description, created_at
            FROM news
            WHERE source_id = %s;
        """
        with conn.cursor() as cur:
            cur.execute(query, (source_id,))
            rows = cur.fetchall()

        return self._rows_to_news_dict(rows)

    def get_existing_urls(self, source_id) -> set:
        """Множество url, уже сохранённых для источника — для дедупликации перед вставкой."""
        conn = self.connect()
        query = "SELECT url FROM news WHERE source_id = %s;"
        with conn.cursor() as cur:
            cur.execute(query, (source_id,))
            return {row[0] for row in cur.fetchall()}

    # ---------- вспомогательные методы ----------

    @staticmethod
    def _rows_to_news_dict(rows) -> dict:
        result = {}
        for row in rows:
            (
                news_id,
                source_id,
                source,
                title,
                url,
                author,
                category,
                description,
                created_at,
            ) = row
            result[news_id] = {
                "source_id": source_id,
                "source": source,
                "title": title,
                "url": url,
                "author": author,
                "category": category,
                "description": description,
                "created_at": created_at,
            }

        return result


if __name__ == "__main__":
    with DBConnection() as db:
        sources = db.get_sources()
        for t in sources:
            print(t, sources[t])

        # news = db.get_news()
        # print(news)