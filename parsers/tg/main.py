
import logging
import re
import sys
from pathlib import Path
from typing import Optional

from tg_parser import Post, get_multiple_channels

# И relevance_detection, и db_connection теперь живут в src/back — унифицированы
# там же, где раньше у каждого парсера была своя копия. Путей нет в sys.path
# ни при запуске `python parsers/tg/main.py` напрямую, ни при импорте модуля
# из run_parsers.py, поэтому прописываем явно здесь (файл остаётся рабочим
# независимо от того, кто и как его импортирует).
_BACK_DIR = Path(__file__).resolve().parents[2] / "src" / "back"
_RELEVANCE_DIR = _BACK_DIR / "relevance_detection"
for _p in (_BACK_DIR, _RELEVANCE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from db_connection import DBConnection  # noqa: E402
from relevance_detector import RelevanceDetector, RelevanceResult  # noqa: E402

# RelevanceDetector отдаёт "medium", БД знает только "mid" — маппинг на границе.
RELEVANCE_TO_DB_PRIORITY: dict[str, str] = {"high": "high", "medium": "mid", "low": "low"}

POSTS_PER_CHANNEL = 30
 
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

        if info.get("status") != "active":
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
 
 
def store_new_posts(
    db: DBConnection, source_id, source_info: dict, posts: list[Post], detector: RelevanceDetector
) -> int:
    """Чистит и вставляет только те посты, которых ещё нет в БД. Возвращает число вставленных."""
    existing_urls = db.get_existing_urls(source_id)
    inserted = 0

    for post in posts:
        if not post.text.strip():
            continue  # медиа-посты без текста пропускаем

        if post.link in existing_urls:
            continue  # уже сохранено раньше

        text = clean_text(post.text)
        relevance: RelevanceResult = detector.detect(source=source_info["name"], title="", text=text)

        db.add_parsed_news(
            source_id=source_id,
            source=source_info["name"],
            title=None,
            text=text,
            url=post.link,
            author=post.forwarded_from or source_info["name"],
            category=None,  # место под будущую классификацию/тегирование
            priority=RELEVANCE_TO_DB_PRIORITY[relevance.relevance],
            relevance_score=relevance.score,
        )
        inserted += 1

    return inserted
 
 
def _run(db: DBConnection, detector: RelevanceDetector) -> None:
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
        inserted = store_new_posts(db, source_id, source_info, posts, detector)
        db.update_source_last_update(source_id)
        total_inserted += inserted
        log.info("[%s] получено постов: %d, новых записей добавлено: %d", username, len(posts), inserted,)

    log.info("Готово. Всего новых записей в БД: %d", total_inserted)


def main(db: Optional[DBConnection] = None, detector: Optional[RelevanceDetector] = None):
    detector = detector or RelevanceDetector()  # тяжёлая инициализация — переиспользуем, если передали снаружи

    if db is not None:
        # Соединение открыл вызывающий код (run_parsers.py) — им и закроется,
        # здесь только используем.
        _run(db, detector)
        return

    with DBConnection() as owned_db:
        _run(owned_db, detector)
 
if __name__ == "__main__":
    main()
