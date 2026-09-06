import argparse
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src" / "back"))

from db_connection import DBConnection  # noqa: E402

from ai.daily_brief import (  # noqa: E402
    MAX_ARTICLES_TO_LLM,
    MIN_RELEVANCE_SCORE,
    generate_daily_brief,
)
from ai.openrouter import DEFAULT_CHAT_MODEL  # noqa: E402

MSK = ZoneInfo("Europe/Moscow")


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=MSK)
    return start, start + timedelta(days=1)


def last_complete_week(today: Optional[date] = None) -> tuple[date, date]:
    """Последняя полная календарная неделя: понедельник–воскресенье."""
    today = today or datetime.now(MSK).date()
    this_monday = today - timedelta(days=today.weekday())
    week_monday = this_monday - timedelta(days=7)
    week_sunday = week_monday + timedelta(days=6)
    return week_monday, week_sunday


def select_brief_news(
    db: DBConnection,
    period_start: datetime,
    period_end: datetime,
    *,
    min_score: float = MIN_RELEVANCE_SCORE,
    limit: int = MAX_ARTICLES_TO_LLM,
) -> list[dict]:
    return db.get_news_for_brief(
        period_start,
        period_end,
        min_score=min_score,
        limit=limit,
    )


def _priority_breakdown(articles: list[dict]) -> dict:
    counts = Counter((a.get("priority") or "low") for a in articles)
    return {"high": counts.get("high", 0), "mid": counts.get("mid", 0), "low": counts.get("low", 0)}


def persist_brief(
    db: DBConnection,
    *,
    report_type: str,
    title: str,
    result: dict,
    articles: list[dict],
    period_start: datetime,
    period_end: datetime,
) -> Optional[int]:
    if result.get("error"):
        status = "failed"
        summary = result["error"]
    else:
        status = "ready"
        summary = result.get("brief") or ""
    used_news = [int(a["id"]) for a in articles if a.get("id") is not None]
    used_sources = sorted(
        {int(a["source_id"]) for a in articles if a.get("source_id") is not None}
    )
    return db.upsert_report(
        report_type=report_type,
        title=title,
        summary=summary,
        period_start=period_start,
        period_end=period_end,
        used_news=used_news,
        used_sources=used_sources,
        status=status,
        priority_breakdown=_priority_breakdown(articles),
    )


def _write_fallback(result: dict, slug: str) -> Path:
    out = ROOT / "ai" / "output"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"brief_{slug}.md"
    text = result.get("brief") or result.get("error") or ""
    path.write_text(text, encoding="utf-8")
    print(f"  fallback file {path}")
    return path


def _persist_or_file(
    db: DBConnection,
    *,
    report_type: str,
    title: str,
    result: dict,
    articles: list[dict],
    period_start: datetime,
    period_end: datetime,
    slug: str,
) -> Optional[int]:
    try:
        return persist_brief(
            db,
            report_type=report_type,
            title=title,
            result=result,
            articles=articles,
            period_start=period_start,
            period_end=period_end,
        )
    except Exception as exc:
        print(f"  persist skip: {exc}")
        _write_fallback(result, slug)
        return None


def daily_range(today: Optional[date] = None, days: int = 7) -> list[date]:
    """Вчера и ещё days-1 суток назад (календарные дни, Europe/Moscow)."""
    today = today or datetime.now(MSK).date()
    yesterday = today - timedelta(days=1)
    return [yesterday - timedelta(days=i) for i in range(days)]


def has_ready_daily(db: DBConnection, day: date) -> bool:
    label = day.isoformat()
    return any(
        item.get("period_start") == label and (item.get("content") or "").strip()
        for item in db.list_reports("daily", include_archived=True)
    )


def run_daily(
    db: DBConnection,
    *,
    day: date,
    model: str,
    dry_run: bool = False,
    skip_existing: bool = False,
) -> dict:
    start, end = _day_bounds(day)
    if skip_existing and has_ready_daily(db, day):
        print(f"[daily {day.isoformat()}] already exists, skip")
        return {"day": day.isoformat(), "skipped": True}
    articles = select_brief_news(db, start, end)
    print(
        f"[daily {day.isoformat()}] score>{MIN_RELEVANCE_SCORE}: "
        f"{len(articles)} новостей (лимит {MAX_ARTICLES_TO_LLM})"
    )
    for a in articles[:8]:
        print(f"  {a['relevance_score']:.2f} | {a['source']} | {(a.get('title') or '')[:70]}")
    if dry_run:
        return {"day": day.isoformat(), "articles": len(articles), "dry_run": True}
    if not articles:
        print(f"  skip empty {day.isoformat()}")
        return {"day": day.isoformat(), "articles": 0, "skipped": True}
    result = generate_daily_brief(
        articles,
        model=model,
        day=day,
        period_label=day.isoformat(),
    )
    result["period_label"] = day.isoformat()
    report_id = _persist_or_file(
        db,
        report_type="daily",
        title=f"Ежедневный бриф {day.isoformat()}",
        result=result,
        articles=articles,
        period_start=start,
        period_end=end,
        slug=f"daily_{day.isoformat()}",
    )
    archived = 0
    try:
        archived = db.archive_old_daily_reports(keep=7)
    except Exception as exc:
        print(f"  archive skip: {exc}")
    print(f"  report id={report_id} archived_old={archived}")
    if result.get("error"):
        print(f"  !! {result['error'][:200]}")
    else:
        print(f"  ok, {len(result.get('brief') or '')} chars")
    return result


def run_weekly(
    db: DBConnection,
    *,
    model: str,
    today: Optional[date] = None,
    dry_run: bool = False,
) -> dict:
    week_mon, week_sun = last_complete_week(today)
    start, _ = _day_bounds(week_mon)
    _, end = _day_bounds(week_sun)
    articles = select_brief_news(db, start, end)
    label = f"{week_mon.isoformat()} — {week_sun.isoformat()}"
    print(
        f"[weekly {label}] score>{MIN_RELEVANCE_SCORE}: "
        f"{len(articles)} новостей (лимит {MAX_ARTICLES_TO_LLM})"
    )
    for a in articles[:8]:
        print(f"  {a['relevance_score']:.2f} | {a['source']} | {(a.get('title') or '')[:70]}")
    if dry_run:
        return {"week": label, "articles": len(articles), "dry_run": True}
    result = generate_daily_brief(
        articles,
        model=model,
        day=week_sun,
        period_label=label,
    )
    result["period_label"] = label
    report_id = _persist_or_file(
        db,
        report_type="weekly",
        title=f"Еженедельный бриф {label}",
        result=result,
        articles=articles,
        period_start=start,
        period_end=end,
        slug=f"weekly_{week_mon.isoformat()}_{week_sun.isoformat()}",
    )
    print(f"  report id={report_id}")
    if result.get("error"):
        print(f"  !! {result['error'][:200]}")
    else:
        print(f"  ok, {len(result.get('brief') or '')} chars")
    return result


def main() -> None:
    p = argparse.ArgumentParser(description="Брифы из БД: daily за вчера, weekly за прошлую календарную неделю")
    p.add_argument("--nightly", action="store_true", help="Вчерашний daily + прошлый пн–вс weekly")
    p.add_argument("--daily", action="store_true")
    p.add_argument("--weekly", action="store_true")
    p.add_argument("--date", help="День daily YYYY-MM-DD (по умолчанию вчера)")
    p.add_argument("--days", type=int, default=1, help="Сколько календарных суток daily считать назад от вчера")
    p.add_argument("--skip-existing", action="store_true", help="Не пересчитывать уже готовый daily")
    p.add_argument("--model", default=DEFAULT_CHAT_MODEL)
    p.add_argument("--dry-run", action="store_true", help="Только показать выборку, без LLM и записи")
    args = p.parse_args()

    today = datetime.now(MSK).date()
    day = date.fromisoformat(args.date) if args.date else today - timedelta(days=1)
    if args.nightly:
        do_daily, do_weekly = True, True
    elif args.daily or args.weekly:
        do_daily, do_weekly = args.daily, args.weekly
    else:
        do_daily, do_weekly = True, False

    db = DBConnection()
    db.connect()
    db.ensure_schema()
    try:
        if do_daily:
            days = daily_range(today, args.days) if args.days > 1 else [day]
            if args.date and args.days <= 1:
                days = [day]
            for one in days:
                run_daily(
                    db,
                    day=one,
                    model=args.model,
                    dry_run=args.dry_run,
                    skip_existing=args.skip_existing,
                )
        if do_weekly:
            run_weekly(db, model=args.model, today=today, dry_run=args.dry_run)
    finally:
        db.close()


if __name__ == "__main__":
    main()
