import psycopg2
import psycopg2.extras
 
 
class DBConnection:
    """
    Класс для подключения к локальной PostgreSQL БД itmo_hack
    и работы с таблицами news и sources.
    """
 
    def __init__(
        self,
        host: str = "localhost",
        dbname: str = "itmo_hack",
        port: int = 5432,
        user: str = "postgres",
        password: str = "1",
    ):
        self.host = host
        self.dbname = dbname
        self.port = port
        self.user = user
        self.password = password
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
            SELECT id, name, url, url_rss, source_type, status,
                   last_update_dt, created_at
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
 
    # ---------- news ----------
 
    def add_news(self, source_id, source, title, url, author, category, description):
        conn = self.connect()
        query = """
            INSERT INTO news
                (source_id, source, title, url, author, category, description)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """

        with conn.cursor() as cur:
            cur.execute(
                query,
                (source_id, source, title, url, author, category, description),
            )
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
 
    # ---------- вспомогательные методы ----------
 
    @staticmethod
    def _rows_to_news_dict(rows) -> dict:
        result = {}
        for row in rows:
            (news_id, source_id, source, title, url, author, category, description) = row
            result[news_id] = {
                "source_id": source_id,
                "source": source,
                "title": title,
                "url": url,
                "author": author,
                "category": category,
                "description": description,
            }

        return result
 
 
if __name__ == "__main__":
    with DBConnection() as db:
        sources = db.get_sources()
        for t in sources:
            print(t, sources[t])
 
        # news = db.get_news()
        # print(news)
