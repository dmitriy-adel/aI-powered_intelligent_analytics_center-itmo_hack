import argparse
import json
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parsers.npa import (  # noqa: E402
    GovernmentParser,
    PravoParser,
    RegulationParser,
    SozdParser,
    fetch_npa_url,
)
from parsers.npa.models import NpaDocument  # noqa: E402

# И relevance_detection, и db_connection теперь живут в src/back — унифицированы
# там же, где раньше у каждого парсера была своя копия.
_BACK_DIR = ROOT / "src" / "back"
_RELEVANCE_DIR = _BACK_DIR / "relevance_detection"
for _p in (_BACK_DIR, _RELEVANCE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from db_connection import DBConnection  # noqa: E402
from relevance_detector import RelevanceDetector, RelevanceResult  # noqa: E402

NPA_SOURCES: dict[str, dict[str, str]] = DBConnection.NPA_SOURCES

RELEVANCE_TO_DB_PRIORITY: dict[str, str] = {"high": "high", "medium": "mid", "low": "low"}

DEFAULT_WATCHLIST = {
    "sozd": ["1215252-8", "1286413-8", "1271570-8"],
    "regulation": ["162556", "169583", "161889"],
    "pravo": ["0001202604130022"],
    "government": [
        "http://government.ru/news/59344/",
        "http://government.ru/news/59377/",
        "https://government.ru/news/59736/",
    ],
}


def _dump(obj) -> dict:
    if obj is None:
        return {}
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return obj


def main() -> None:
    p = argparse.ArgumentParser(description="Fetch NPA from official registries")
    p.add_argument("--sozd", nargs="*", help="Номера законопроектов СОЗД")
    p.add_argument("--regulation", nargs="*", help="ID проектов regulation.gov.ru")
    p.add_argument("--regulation-search", help="Поиск на regulation.gov.ru")
    p.add_argument("--pravo", nargs="*", help="eoNumber publication.pravo.gov.ru")
    p.add_argument("--pravo-search-name", help="Поиск по названию на pravo.gov.ru")
    p.add_argument("--pravo-search-number", help="Поиск по номеру акта")
    p.add_argument("--government-limit", type=int, help="Сколько анонсов из RSS government.ru")
    p.add_argument("--government", nargs="*", help="URL новостей government.ru")
    p.add_argument("--url", help="Один URL — диспетчер по домену")
    p.add_argument("--watchlist", action="store_true", help="Демо-набор из Excel кейсодателя")
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "ai" / "output" / "npa_fetched.json",
    )
    args = p.parse_args()

    results: list[dict] = []

    if args.url:
        doc = fetch_npa_url(args.url)
        if doc:
            results.append(_dump(doc))
        else:
            print(f"Unknown or empty: {args.url}")

    sozd_ids = list(args.sozd or [])
    reg_ids = list(args.regulation or [])
    pravo_ids = list(args.pravo or [])
    gov_urls = list(args.government or [])

    if args.watchlist:
        sozd_ids += DEFAULT_WATCHLIST["sozd"]
        reg_ids += DEFAULT_WATCHLIST["regulation"]
        pravo_ids += DEFAULT_WATCHLIST["pravo"]
        gov_urls += DEFAULT_WATCHLIST["government"]

    if sozd_ids:
        parser = SozdParser()
        for number in dict.fromkeys(sozd_ids):
            print(f"[sozd] {number}")
            results.append(_dump(parser.get_bill(number)))

    if reg_ids:
        parser = RegulationParser()
        for pid in dict.fromkeys(reg_ids):
            print(f"[regulation] {pid}")
            doc = parser.get_project(pid)
            if doc:
                results.append(_dump(doc))
            else:
                print(f"  !! not found")

    if args.regulation_search:
        print(f"[regulation search] {args.regulation_search}")
        for doc in RegulationParser().search(args.regulation_search, limit=10):
            results.append(_dump(doc))

    if pravo_ids:
        parser = PravoParser()
        for eo in dict.fromkeys(pravo_ids):
            print(f"[pravo] {eo}")
            doc = parser.get_document(eo)
            if doc:
                results.append(_dump(doc))
            else:
                print("  !! not found")

    if args.pravo_search_name or args.pravo_search_number:
        print("[pravo search]")
        for doc in PravoParser().search(
            name=args.pravo_search_name,
            number=args.pravo_search_number,
        ):
            results.append(_dump(doc))

    if args.government_limit:
        print(f"[government rss] limit={args.government_limit}")
        rss_docs = GovernmentParser().fetch_rss(limit=args.government_limit)
        for doc in rss_docs:
            article = GovernmentParser().fetch_article(doc.link)
            results.append(_dump(article or doc))

    if gov_urls:
        parser = GovernmentParser()
        for url in dict.fromkeys(gov_urls):
            print(f"[government] {url}")
            doc = parser.fetch_article(url)
            if doc:
                results.append(_dump(doc))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {len(results)} documents -> {args.out}")
    for item in results:
        ev = len(item.get("events") or [])
        print(f"  {item.get('id_type')} {item.get('official_id')} | events={ev} | {item.get('title','')[:70]}")


def _fetch_watchlist_documents(watchlist: dict) -> list[NpaDocument]:
    """Тянет документы по watchlist через уже существующие парсеры — без записи в БД/файл."""
    docs: list[NpaDocument] = []

    sozd_ids = list(watchlist.get("sozd") or [])
    if sozd_ids:
        parser = SozdParser()
        for number in dict.fromkeys(sozd_ids):
            doc = parser.get_bill(number)
            if doc:
                docs.append(doc)

    reg_ids = list(watchlist.get("regulation") or [])
    if reg_ids:
        parser = RegulationParser()
        for pid in dict.fromkeys(reg_ids):
            doc = parser.get_project(pid)
            if doc:
                docs.append(doc)

    pravo_ids = list(watchlist.get("pravo") or [])
    if pravo_ids:
        parser = PravoParser()
        for eo in dict.fromkeys(pravo_ids):
            doc = parser.get_document(eo)
            if doc:
                docs.append(doc)

    gov_urls = list(watchlist.get("government") or [])
    if gov_urls:
        parser = GovernmentParser()
        for url in dict.fromkeys(gov_urls):
            doc = parser.fetch_article(url)
            if doc:
                docs.append(doc)

    return docs


def collect_and_store(
    db: Optional[DBConnection] = None,
    detector: Optional[RelevanceDetector] = None,
    watchlist: Optional[dict] = None,
) -> int:
    """
    DB-версия сбора: те же источники, что в main() (по watchlist), но вместо
    дампа в JSON — сразу проставление релевантности и запись в news.

    watchlist по умолчанию — DEFAULT_WATCHLIST (демо-набор кейсодателя).
    В отличие от tg/web, NPA сейчас не полит RSS/каналы, а тянет фиксированный
    список ID из реестров — на будущее watchlist стоит вынести в БД/конфиг,
    чтобы список отслеживаемых законопроектов/актов не жил в коде.
    """
    own_db = db is None
    db = db or DBConnection()
    detector = detector or RelevanceDetector()  # тяжёлая инициализация — переиспользуем, если передали снаружи
    watchlist = watchlist if watchlist is not None else DEFAULT_WATCHLIST

    try:
        source_ids = db.ensure_npa_sources()
        existing_urls = {domain: db.get_existing_urls(sid) for domain, sid in source_ids.items()}

        docs = _fetch_watchlist_documents(watchlist)

        inserted = 0
        for doc in docs:
            article = doc.to_article()
            domain = article["source"]

            source_id = source_ids.get(domain)
            if source_id is None:
                print(f"  !! неизвестный источник НПА: {domain!r}, пропускаю")
                continue

            link = article.get("link")
            if not link or link in existing_urls[domain]:
                continue

            source_name = NPA_SOURCES[domain]["name"]
            text = article.get("text") or article.get("description") or ""
            relevance: RelevanceResult = detector.detect(
                source=source_name, title=article.get("title") or "", text=text
            )

            db.add_parsed_news(
                source_id=source_id,
                source=source_name,
                title=article.get("title"),
                url=link,
                author=article.get("author"),
                category=article.get("category"),
                text=text,
                priority=RELEVANCE_TO_DB_PRIORITY[relevance.relevance],
                relevance_score=relevance.score,
            )
            existing_urls[domain].add(link)
            inserted += 1
            print(f"  [{source_name}] сохранено: {article.get('title', '')[:70]}")

        for source_id in source_ids.values():
            db.update_source_last_update(source_id)

        print(f"Готово. Всего новых записей в БД: {inserted}")
        return inserted
    finally:
        if own_db:
            db.close()


if __name__ == "__main__":
    main()
