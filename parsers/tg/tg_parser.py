
import argparse
import json
import random
import time
from dataclasses import dataclass, asdict
from typing import Optional
 
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
 
BASE_URL = "https://t.me/s/{channel}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}
 
 
def make_session() -> requests.Session:
    """Session с автоматическим retry+backoff на 429/5xx и переиспользуемым соединением."""
    session = requests.Session()
    session.headers.update(HEADERS)
    retry = Retry(
        total=5,
        backoff_factor=2,  # 2s, 4s, 8s, 16s, 32s между повторами
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,  # если сервер сам сказал Retry-After — слушаем его
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session
 
 
class RateLimiter:
    """Один общий лимитер на ВСЕ запросы, независимо от канала — не по каждому отдельно."""
 
    def __init__(self, base_delay: float = 1.5, jitter: float = 0.7):
        self.base_delay = base_delay
        self.jitter = jitter
        self._last_call = 0.0
 
    def wait(self):
        elapsed = time.monotonic() - self._last_call
        delay = self.base_delay + random.uniform(0, self.jitter)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_call = time.monotonic()
 
 
@dataclass
class Post:
    channel: str
    post_id: int
    date: Optional[str]
    text: str
    views: Optional[str]
    forwarded_from: Optional[str]
    link: str
 
 
def fetch_page(session: requests.Session, channel: str, before: Optional[int] = None) -> str:
    url = BASE_URL.format(channel=channel)
    params = {"before": before} if before else {}
    resp = session.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.text
 
 
def parse_posts(html: str, channel: str) -> list[Post]:
    soup = BeautifulSoup(html, "lxml")
    posts = []
 
    for block in soup.select("div.tgme_widget_message"):
        data_post = block.get("data-post", "")  # формат "channel/123"
        post_id = int(data_post.split("/")[-1]) if "/" in data_post else None
        if post_id is None:
            continue
 
        text_el = block.select_one(".tgme_widget_message_text")
        text = text_el.get_text("\n", strip=True) if text_el else ""
 
        time_el = block.select_one("time.time")
        date = time_el.get("datetime") if time_el else None
 
        views_el = block.select_one(".tgme_widget_message_views")
        views = views_el.get_text(strip=True) if views_el else None
 
        fwd_el = block.select_one(".tgme_widget_message_forwarded_from_name")
        forwarded_from = fwd_el.get_text(strip=True) if fwd_el else None
 
        posts.append(
            Post(
                channel=channel,
                post_id=post_id,
                date=date,
                text=text,
                views=views,
                forwarded_from=forwarded_from,
                link=f"https://t.me/{channel}/{post_id}",
            )
        )
 
    return posts
 
 
def get_channel_messages(
    channel: str,
    limit: int = 50,
    session: Optional[requests.Session] = None,
    limiter: Optional[RateLimiter] = None,
) -> list[Post]:
    """Собирает сообщения канала, листая историю назад через ?before=."""
    session = session or make_session()
    limiter = limiter or RateLimiter()
    all_posts: dict[int, Post] = {}
    before = None
 
    while len(all_posts) < limit:
        limiter.wait()  # пауза ПЕРЕД каждым запросом, общая на весь процесс
        html = fetch_page(session, channel, before)
        batch = parse_posts(html, channel)
 
        if not batch:
            break  # дальше постов нет
 
        new_ids = [p.post_id for p in batch if p.post_id not in all_posts]
        for p in batch:
            all_posts[p.post_id] = p
 
        if not new_ids:
            break  # повторная страница — дошли до конца истории
 
        before = min(all_posts.keys())  # следующая порция — более старые посты
 
    # сортируем от новых к старым и обрезаем до limit
    ordered = sorted(all_posts.values(), key=lambda p: p.post_id, reverse=True)
    return ordered[:limit]
 
 
def get_multiple_channels(
    channels: list[str], limit: int = 50
) -> dict[str, list[Post]]:
    """
    Обходит несколько каналов ПОСЛЕДОВАТЕЛЬНО с одним общим rate-limiter'ом.
    Именно так, а не в отдельных потоках на канал — см. пояснение в комментариях выше:
    все каналы бьют в один и тот же сервер, поэтому лимит должен быть общим.
    """
    session = make_session()
    limiter = RateLimiter(base_delay=1.5, jitter=0.7)
    result = {}
    for channel in channels:
        try:
            result[channel] = get_channel_messages(channel, limit, session, limiter)
        except requests.HTTPError as e:
            print(f"[{channel}] ошибка запроса: {e}")
            result[channel] = []
    return result
 
 
def main():
    parser = argparse.ArgumentParser(description="Парсер публичного Telegram-канала")
    parser.add_argument("channel", help="username канала без @, например rfrit")
    parser.add_argument("--limit", type=int, default=50, help="сколько последних постов собрать")
    parser.add_argument("--out", default=None, help="путь к JSON-файлу для сохранения")
    args = parser.parse_args()
 
    posts = get_channel_messages(args.channel, limit=args.limit)
    # для одного канала это по-прежнему работает: session/limiter создаются внутри
 
    print(f"Собрано постов: {len(posts)}")
    for p in posts[:5]:
        preview = (p.text[:80] + "…") if len(p.text) > 80 else p.text
        print(f"[{p.date}] {preview}")
 
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump([asdict(p) for p in posts], f, ensure_ascii=False, indent=2)
            
        print(f"Сохранено в {args.out}")
 
 
if __name__ == "__main__":
    main()