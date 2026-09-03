
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
 
from db_connection import DBConnection
from web_parsers import DEFAULT_DELAY, WebParsers, _resolve_source
 

ITEMS_PER_SOURCE = 10
 
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
        if not info.get("status"):
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
 
 
def process_source(spec: dict, source_id: int, source_info: dict) -> int:
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
 
            db.add_news(
                source_id=source_id,
                source=source_info["name"],
                title=clean_text(item.get("title")) or "no-title",
                url=url,
                author=item.get("author") or source_info["name"],
                category=item.get("category"),
                text=clean_text(body),
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
 
 
def main():
    with DBConnection() as db:
        tasks = collect_web_sources(db)
 
    if not tasks:
        log.warning("Не нашлось активных веб-источников, совпадающих с web_parser.SOURCES")
        return
 
    log.info("Запускаю сбор по %d источникам: %s", len(tasks), [t[2]["name"] for t in tasks])
 
    total_inserted = 0
    with ThreadPoolExecutor(max_workers=len(tasks), thread_name_prefix="src") as executor:
        futures = {
            executor.submit(process_source, spec, source_id, source_info): source_info["name"]
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
 