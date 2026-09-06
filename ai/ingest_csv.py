import csv
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src" / "back"))

from db_connection import DBConnection  # noqa: E402

OUT = ROOT / "ai" / "output"
MSK = ZoneInfo("Europe/Moscow")

REL_TO_SCORE = {"high": 0.9, "medium": 0.7, "low": 0.55, "noise": 0.15}

SOURCE_META = {
    "Ведомости": ("https://www.vedomosti.ru/", "СМИ", "Экономика"),
    "Коммерсантъ": ("https://www.kommersant.ru/", "СМИ", "Экономика"),
    "Телеспутник": ("https://telesputnik.ru/", "СМИ", "Технологии"),
    "Кабельщик": ("https://www.cableman.ru/", "СМИ", "Технологии"),
    "АРПП - новости": ("https://t.me/arppsoft", "СМИ", "Технологии"),
    "Цифровые индустриальные технологии - дайджест": ("https://t.me/cit_gov", "Telegram", "Технологии"),
    "РФРИТ": ("https://t.me/rfrit", "Telegram", "Технологии"),
    "Гранты для ИТ": ("https://t.me/grantsforbussines", "Telegram", "Технологии"),
    "CIO: канал IT руководителей": ("https://t.me/cio_channel", "Telegram", "Технологии"),
    "Торгпред - тендеры и закупки": ("https://t.me/rustorgpred", "Telegram", "Технологии"),
    "АРПЭ - новости": ("https://t.me/arperf", "Telegram", "Технологии"),
    "ЦИПР - новости и анонсы мероприятий": ("https://t.me/icipr", "Telegram", "Технологии"),
    "government.ru": ("http://government.ru/news/", "Регулятор", "Регулирование"),
    "regulation.gov.ru": ("https://regulation.gov.ru/", "Регулятор", "Регулирование"),
    "СОЗД Госдумы": ("https://sozd.duma.gov.ru/", "Регулятор", "Регулирование"),
    "publication.pravo.gov.ru": ("https://publication.pravo.gov.ru/", "Регулятор", "Регулирование"),
}


def _tags(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "да"}


def _strip_brief_header(text: str) -> str:
    lines = text.splitlines()
    while lines and (not lines[0].strip() or lines[0].startswith("#") or lines[0].startswith("**")):
        lines.pop(0)
    if lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines).strip() or text.strip()


def load_rows() -> list[dict]:
    rows: list[dict] = []
    for name in ("smi_ui_cards.csv", "npa_ui_cards.csv"):
        path = OUT / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def ingest_news(db: DBConnection, rows: list[dict]) -> tuple[int, int]:
    conn = db.connect()
    with conn.cursor() as cur:
        cur.execute("UPDATE news SET in_general = FALSE WHERE in_general;")
    conn.commit()

    cache: dict[str, int] = {}
    inserted = 0
    skipped = 0
    seen: set[str] = set()
    for row in rows:
        name = (row.get("source_name") or "").strip()
        url = (row.get("link") or "").strip()
        if not name or not url or url in seen:
            skipped += 1
            continue
        seen.add(url)
        if name not in cache:
            url_src, source_type, category = SOURCE_META.get(
                name, ("", "СМИ", row.get("category") or "Экономика")
            )
            cache[name] = db.get_or_create_source(
                name=name,
                url=url_src,
                source_type=source_type,
                category_default=category,
            )
        rel = (row.get("relevance_to_company") or "").strip().lower()
        db.upsert_news_from_csv(
            source_id=cache[name],
            source=name,
            title=row.get("title") or row.get("title_original") or "",
            url=url,
            author=row.get("author") or "—",
            category=row.get("category") or SOURCE_META.get(name, ("", "", "Экономика"))[2],
            description=row.get("description") or "",
            text=row.get("text") or "",
            pub_date=db._parse_pub_date(row.get("pub_date")),
            who=row.get("who") or None,
            what=row.get("what") or None,
            when=row.get("when") or None,
            consequences=row.get("consequences") or None,
            tags=_tags(row.get("tags") or ""),
            importance=row.get("importance") or None,
            in_general=_truthy(row.get("in_general")),
            relevance_score=REL_TO_SCORE.get(rel, 0.0),
        )
        inserted += 1
    return inserted, skipped


def ingest_briefs(db: DBConnection) -> int:
    path = OUT / "briefs.csv"
    if not path.exists():
        print("  skip missing briefs.csv")
        return 0
    written = 0
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            summary = (row.get("content") or "").strip()
            if not summary or "подходящих новостей нет" in summary.lower():
                continue
            report_type = (row.get("report_type") or "daily").strip()
            start_d = date.fromisoformat(row["period_start"])
            end_d = date.fromisoformat(row["period_end"])
            start = datetime(start_d.year, start_d.month, start_d.day, tzinfo=MSK)
            # period_end в CSV — включительный календарный день
            end = datetime(end_d.year, end_d.month, end_d.day, tzinfo=MSK) + timedelta(days=1)
            db.upsert_report(
                report_type=report_type,
                title=row.get("title") or f"{report_type} {row.get('period_start')}",
                summary=summary,
                period_start=start,
                period_end=end,
                used_news=[],
                used_sources=[],
                status=row.get("status") or "ready",
            )
            written += 1
            print(f"  report {report_type} {row.get('period_start')} <- briefs.csv")
    return written


def main() -> None:
    rows = load_rows()
    print(f"CSV rows: {len(rows)}")
    db = DBConnection()
    db.connect()
    db.ensure_schema()
    try:
        upserted, skipped = ingest_news(db, rows)
        reports = ingest_briefs(db)
        conn = db.connect()
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM news")
            news_n = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM news WHERE in_general AND NOT is_hidden")
            general_n = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM reports")
            reports_n = cur.fetchone()[0]
        print(f"upserted={upserted} skipped={skipped}")
        print(f"db news={news_n} general={general_n} reports={reports_n} briefs_written={reports}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
