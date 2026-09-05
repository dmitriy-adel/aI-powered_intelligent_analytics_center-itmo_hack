import logging
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from web_parsers import DEFAULT_DELAY, WebParsers, _resolve_source

# И relevance_detection, и db_connection теперь живут в src/back — унифицированы
# там же, где раньше у каждого парсера была своя копия.
_BACK_DIR = Path(__file__).resolve().parents[2] / "src" / "back"
_RELEVANCE_DIR = _BACK_DIR / "relevance_detection"
for _p in (_BACK_DIR, _RELEVANCE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from db_connection import DBConnection  # noqa: E402
from relevance_detector import RelevanceDetector, RelevanceResult  # noqa: E402

RELEVANCE_TO_DB_PRIORITY: dict[str, str] = {"high": "high", "medium": "mid", "low": "low"}

# detector использует общие на уровне модуля объекты Natasha NER и
# pymorphy3.MorphAnalyzer (см. relevance_detection/entity_extraction.py,
# similarity.py) — их потокобезопасность под конкурентными вызовами не
# гарантирована и не проверялась, а process_source работает в пуле потоков
# (по одному на источник). Лок сериализует именно расчёт релевантности
# (десятки мс), сетевой I/O парсеров как был параллельным, так и остаётся.
_detector_lock = threading.Lock()

ITEMS_PER_SOURCE = 30
 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
)
log = logging.getLogger("web_news_collector")
 
 
def clean_text(text: Optional[str]) -> str:
    """'\n' -> пробел, схлопывание повторяющихся пробелов, обрезка краёв."""
    if not text:
        return ""
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()
 
 
def collect_web_sources(db: DBConnection) -> list[tuple[dict, int, dict]]:
    """
    Сопоставляет записи sources с известными web_parser.SOURCES конфигурациями
    по домену (пробуем url_rss, затем url). Источники, для которых нет
    подходящей конфигурации (например, telegram-каналы), просто пропускаются.
    """
    sources = db.get_sources()
    tasks = []
 
    for source_id, info in sources.items():
        if info.get("status") != "active":
            continue
 
        candidate_url = info.get("url_rss") or info.get("url")
        if not candidate_url:
            continue
 
        try:
            matched = _resolve_source(candidate_url)
        
        except ValueError:
            continue  
 
        spec = {
            "url": info.get("url_rss") or matched.rss_url,
            "limit": ITEMS_PER_SOURCE,
            "until": info.get("last_update_dt"),  
            "delay": DEFAULT_DELAY,
        }
        tasks.append((spec, source_id, info))
 
    return tasks
 
 
def process_source(spec: dict, source_id: int, source_info: dict, detector: RelevanceDetector) -> int:
    """Полностью обрабатывает один источник в своём потоке: своё соединение с БД,
    свой WebParsers, запись каждой новости сразу по готовности."""
    inserted = 0
 
    with DBConnection() as db:
        existing_urls = db.get_existing_urls(source_id)
        parser = WebParsers()
 
        def on_item(item: dict) -> None:
            nonlocal inserted
 
            url = item.get("link")
            if not url or url in existing_urls:
                return  

            body = item.get("text") or item.get("description") or ""
            title = clean_text(item.get("title")) or "no-title"
            cleaned_body = clean_text(body)

            with _detector_lock:
                relevance: RelevanceResult = detector.detect(
                    source=source_info["name"], title=title, text=cleaned_body
                )
 
            db.add_parsed_news(
                source_id=source_id,
                source=source_info["name"],
                title=title,
                url=url,
                author=item.get("author") or source_info["name"],
                category=item.get("category"),
                text=cleaned_body,
                priority=RELEVANCE_TO_DB_PRIORITY[relevance.relevance],
                relevance_score=relevance.score,
            )
            existing_urls.add(url)
            inserted += 1
            log.info("[%s] сохранено: %s", source_info["name"], item.get("title"))
 
        try:
            parser.parse_page(
                url=spec["url"],
                limit=spec.get("limit"),
                until=spec.get("until"),
                delay=spec.get("delay", DEFAULT_DELAY),
                on_item=on_item,
            )
        except Exception:
            log.exception("[%s] ошибка при сборе источника", source_info["name"])
            raise
        
        finally:
            db.update_source_last_update(source_id)
 
    return inserted
 
 
def main(db: Optional[DBConnection] = None, detector: Optional[RelevanceDetector] = None):
    detector = detector or RelevanceDetector()  # тяжёлая инициализация — переиспользуем, если передали снаружи

    if db is not None:
        tasks = collect_web_sources(db)
    else:
        with DBConnection() as owned_db:
            tasks = collect_web_sources(owned_db)
 
    if not tasks:
        log.warning("Не нашлось активных веб-источников, совпадающих с web_parser.SOURCES")
        return
 
    log.info("Запускаю сбор по %d источникам: %s", len(tasks), [t[2]["name"] for t in tasks])
 
    total_inserted = 0
    # Каждый источник — свой поток и своё соединение с БД (process_source
    # открывает `with DBConnection()` сама): psycopg2-соединение нельзя делить
    # между потоками, это осталось так же, как и до унификации db_connection.
    with ThreadPoolExecutor(max_workers=len(tasks), thread_name_prefix="src") as executor:
        futures = {
            executor.submit(process_source, spec, source_id, source_info, detector): source_info["name"]
            for spec, source_id, source_info in tasks
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                inserted = future.result()

            except Exception:
                log.exception("[%s] источник завершился с ошибкой, пропускаю", name)
                continue

            total_inserted += inserted
 
    log.info("Готово. Всего новых записей в БД: %d", total_inserted)
 
 
if __name__ == "__main__":
    main()
 