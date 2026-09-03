
import logging
import re
from typing import Optional
 
from db_connection import DBConnection
from tg_parser import Post, get_multiple_channels
 

POSTS_PER_CHANNEL = 20
 
CHANNEL_URL_RE = re.compile(r"t\.me/(?:s/)?([A-Za-z0-9_]+)")
 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("news_collector")
 
 
def clean_text(text: str) -> str:
    """'\n' -> пробел, схлопывание повторяющихся пробелов, обрезка краёв."""
    if not text:
        return ""
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()
 
 
def extract_channel_username(url: str) -> Optional[str]:
    if not url:
        return None
    match = CHANNEL_URL_RE.search(url)
    return match.group(1) if match else None
 
 
def collect_telegram_sources(db: DBConnection) -> dict:
    sources = db.get_sources()
    mapping = {}
    for source_id, info in sources.items():
        if info.get("source_type") != "Telegram":
            continue

        if not info.get("status"):
            continue
        
        username = extract_channel_username(info.get("url", ""))
        if username:
            mapping[username] = (source_id, info)
        
        else:
            log.warning(
                "Не удалось извлечь username канала из url=%r (source_id=%s)",
                info.get("url"),
                source_id,
            )
    return mapping
 
 
def store_new_posts(db: DBConnection, source_id, source_info: dict, posts: list[Post]) -> int:
    """Чистит и вставляет только те посты, которых ещё нет в БД. Возвращает число вставленных."""
    existing_urls = db.get_existing_urls(source_id)
    inserted = 0

    for post in posts:
        if not post.text.strip():
            continue  # медиа-посты без текста пропускаем

        if post.link in existing_urls:
            continue  # уже сохранено раньше

        db.add_news(
            source_id=source_id,
            source=source_info["name"],
            title=None,
            text=clean_text(post.text),
            url=post.link,
            author=post.forwarded_from or source_info["name"],
            category=None,  # место под будущую классификацию/тегирование
        )
        inserted += 1

    return inserted
 
 
def main():
    with DBConnection() as db:
        channel_map = collect_telegram_sources(db)
 
        if not channel_map:
            log.warning("Нет активных telegram-источников в таблице sources — нечего собирать")
            return
 
        channels = list(channel_map.keys())
        log.info("Собираю посты из каналов: %s", channels)
 
        posts_by_channel = get_multiple_channels(channels, limit=POSTS_PER_CHANNEL)
 
        total_inserted = 0
        for username, posts in posts_by_channel.items():
            source_id, source_info = channel_map[username]
            inserted = store_new_posts(db, source_id, source_info, posts)
            db.update_source_last_update(source_id)
            total_inserted += inserted
            log.info("[%s] получено постов: %d, новых записей добавлено: %d", username, len(posts), inserted,)
 
        log.info("Готово. Всего новых записей в БД: %d", total_inserted)
 
if __name__ == "__main__":
    main()
