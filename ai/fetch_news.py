import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "parsers" / "web"))

from web_parsers import SOURCES, WebParsers  # noqa: E402

DEFAULT_SOURCES = [
    {"url": "https://www.vedomosti.ru/rss/news.xml", "limit": 2, "delay": 1},
    {"url": "https://www.kommersant.ru/rss/news.xml", "limit": 2, "delay": 1},
    {"url": "https://telesputnik.ru/rss/", "limit": 2, "delay": 1},
]


def parse_since(value: str) -> datetime:
    """Парсит --since: yesterday | YYYY-MM-DD | ISO datetime."""
    value = value.strip().lower()
    now = datetime.now(timezone.utc)
    if value == "yesterday":
        d = (now - timedelta(days=1)).date()
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    if value == "today":
        d = now.date()
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    if len(value) == 10:
        d = date.fromisoformat(value)
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def all_rss_sources(*, limit: int = 30, delay: float = 1.0, since: Optional[datetime] = None) -> list[dict]:
    spec = []
    for src in SOURCES:
        entry: dict = {"url": src.rss_url, "limit": limit, "delay": delay}
        if since is not None:
            entry["until"] = since
        spec.append(entry)
    return spec


def fetch_news(
    *,
    per_source: int = 2,
    delay: float = 1.0,
    since: Optional[datetime] = None,
    output_dir: Optional[Path] = None,
) -> list[dict]:
    spec = all_rss_sources(limit=per_source, delay=delay, since=since)
    parser = WebParsers()
    grouped = parser.parse_many(spec, max_workers=len(spec))

    items: list[dict] = []
    for source_name, news_list in grouped.items():
        for item in news_list:
            item["_fetched_at"] = datetime.now(timezone.utc).isoformat()
            if since is not None:
                item["_since_filter"] = since.isoformat()
            if not item.get("text"):
                item["_parse_warning"] = "empty_body"
            items.append(item)

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = ""
        if since is not None:
            suffix = f"_{since.date().isoformat()}"
        out_path = output_dir / f"raw_news{suffix}.json"
        out_path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Saved {len(items)} articles -> {out_path}")

    return items


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Fetch news from RSS parsers")
    p.add_argument("--per-source", type=int, default=2)
    p.add_argument("--delay", type=float, default=1.0)
    p.add_argument(
        "--since",
        help="Фильтр по дате: yesterday | YYYY-MM-DD | ISO datetime (pubDate >= since)",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "ai" / "output",
    )
    args = p.parse_args()
    since_dt = parse_since(args.since) if args.since else None
    fetch_news(
        per_source=args.per_source,
        delay=args.delay,
        since=since_dt,
        output_dir=args.output_dir,
    )
