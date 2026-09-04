import argparse
import json
import sys
from pathlib import Path

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


if __name__ == "__main__":
    main()
