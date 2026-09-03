import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "parsers" / "web"))

from web_parsers import SOURCES, WebParsers


def parse_since(value: str) -> datetime:
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


def fetch_news(
    *,
    per_source: int = 2,
    delay: float = 1.0,
    since: datetime | None = None,
    output_dir: Path | None = None,
) -> list[dict]:
    spec = []
    for src in SOURCES:
        entry = {"url": src.rss_url, "limit": per_source, "delay": delay}
        if since is not None:
            entry["until"] = since
        spec.append(entry)
    parser = WebParsers()
    grouped = parser.parse_many(spec, max_workers=len(spec))

    items = []
    for news_list in grouped.values():
        for item in news_list:
            item["_fetched_at"] = datetime.now(timezone.utc).isoformat()
            if since is not None:
                item["_since_filter"] = since.isoformat()
            if not item.get("text"):
                item["_parse_warning"] = "empty_body"
            items.append(item)

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = f"_{since.date().isoformat()}" if since is not None else ""
        out_path = output_dir / f"raw_news{suffix}.json"
        out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved {len(items)} articles -> {out_path}")

    return items


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--per-source", type=int, default=2)
    p.add_argument("--delay", type=float, default=1.0)
    p.add_argument("--since")
    p.add_argument("--output-dir", type=Path, default=ROOT / "ai" / "output")
    args = p.parse_args()
    since_dt = parse_since(args.since) if args.since else None
    fetch_news(
        per_source=args.per_source,
        delay=args.delay,
        since=since_dt,
        output_dir=args.output_dir,
    )
