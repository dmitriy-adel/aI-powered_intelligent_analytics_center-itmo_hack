import argparse
import importlib.util
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "src" / "back"))
from db_connection import DBConnection as ApiDB  # noqa: E402

sys.path.insert(0, str(ROOT / "parsers" / "web"))
from web_parsers import WebParsers, _resolve_source  # noqa: E402

from parsers.npa import GovernmentParser, PravoParser, RegulationParser, SozdParser  # noqa: E402
from ai.enrich import enrich_one, load_company_profile  # noqa: E402
from ai.entity_store import PostgresEntityStore  # noqa: E402
from ai.link_npa import link_one  # noqa: E402
from ai.openrouter import DEFAULT_CHAT_MODEL, OpenRouterError  # noqa: E402

def _load_parser_db():
    spec = importlib.util.spec_from_file_location(
        "web_parser_dbconn", ROOT / "parsers" / "web" / "db_connection.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.DBConnection

ParserDB = _load_parser_db()

def clean_text(text) -> str:
    if not text:
        return ""
    text = text.replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()

HOST_HINTS = (
    ("vedomosti.ru", "Ведомости"),
    ("kommersant.ru", "Коммерсант"),
    ("telesputnik.ru", "Телеспутник"),
    ("regulation.gov.ru", "regulation.gov.ru"),
    ("sozd.duma.gov.ru", "СОЗД"),
    ("publication.pravo.gov.ru", "publication.pravo.gov.ru"),
    ("government.ru", "government.ru"),
)

def _match_source(sources: dict, *, url: str = "", name_hint: str = "") -> tuple[int, dict]:
    host = urlparse(url or "").netloc.lower()
    for sid, info in sources.items():
        blob = " ".join(
            str(info.get(k) or "") for k in ("name", "url", "url_rss")
        ).lower()
        if host and host in blob:
            return sid, info
        if name_hint and name_hint.lower() in (info.get("name") or "").lower():
            return sid, info
    for needle, hint in HOST_HINTS:
        if needle in host or needle in (url or "").lower():
            return _match_source(sources, name_hint=hint)
    raise KeyError(f"Нет источника в БД для url={url!r} hint={name_hint!r}")

def _insert_item(db: ParserDB, sources: dict, item: dict, *, source_url: str = "") -> Optional[int]:
    url = item.get("link") or item.get("url")
    if not url:
        return None
    sid, info = _match_source(sources, url=source_url or url, name_hint=item.get("source") or "")
    if url in db.get_existing_urls(sid):
        return None
    body = item.get("text") or item.get("description") or item.get("summary") or ""
    news_id = db.add_news(
        source_id=sid,
        source=info["name"],
        title=clean_text(item.get("title")) or "Без заголовка",
        url=url,
        author=item.get("author") or item.get("department") or info["name"],
        category=item.get("category") or info.get("category_default") or "Экономика",
        text=clean_text(body),
    )
    return news_id

def collect_web(*, per_source: int, delay: float) -> int:
    parser = WebParsers()
    inserted = 0
    with ParserDB() as db:
        sources = db.get_sources()
        tasks = []
        for sid, info in sources.items():
            if info.get("status") != "active":
                continue
            candidate = info.get("url_rss") or info.get("url")
            if not candidate:
                continue
            try:
                matched = _resolve_source(candidate)
            except ValueError:
                continue
            tasks.append((info, matched.rss_url or candidate))

        def run(pair):
            info, rss = pair
            items = parser.parse_page(url=rss, limit=per_source, delay=delay)
            n = 0
            with ParserDB() as local:
                srcs = local.get_sources()
                for item in items:
                    if _insert_item(local, srcs, item, source_url=rss):
                        n += 1
            return info["name"], n, len(items)

        with ThreadPoolExecutor(max_workers=max(1, len(tasks))) as pool:
            futs = [pool.submit(run, t) for t in tasks]
            for fut in as_completed(futs):
                name, n, total = fut.result()
                print(f"[web] {name}: +{n} из {total}")
                inserted += n
    return inserted

def collect_npa(
    *,
    regulation_limit: int = 8,
    sozd_limit: int = 4,
    government_limit: int = 4,
    pravo_pages: int = 0,
    model: str = DEFAULT_CHAT_MODEL,
) -> int:
    """Официальные реестры → news → сразу склейка в entities (с полным timeline)."""
    import time

    api = ApiDB()
    api.connect()
    api.ensure_schema()
    store = PostgresEntityStore(api)

    docs: list = []
    if regulation_limit:
        print(f"[npa] regulation.gov.ru list_recent {regulation_limit}")
        remaining = regulation_limit
        offset = 0
        while remaining > 0:
            batch = min(100, remaining)
            chunk = RegulationParser().list_recent(limit=batch, offset=offset)
            if not chunk:
                break
            docs.extend(chunk)
            offset += len(chunk)
            remaining -= len(chunk)
            if len(chunk) < batch:
                break

    sozd_ids = list(dict.fromkeys(["1215252-8", "1286413-8", "1271570-8"]))
    if sozd_limit:
        try:
            sozd_ids.extend(SozdParser().recent_bill_numbers(limit=max(sozd_limit, 10)))
        except Exception as exc:  # noqa: BLE001
            print(f"[npa] sozd homepage: {exc}")
    sozd_ids = list(dict.fromkeys(sozd_ids))[: max(sozd_limit, 3)]
    sozd = SozdParser()
    for number in sozd_ids:
        print(f"[npa] sozd {number}")
        try:
            docs.append(sozd.get_bill(number))
        except Exception as exc:  # noqa: BLE001
            print(f"  !! {exc}")
        time.sleep(0.35)

    if pravo_pages:
        print(f"[npa] pravo pages={pravo_pages}")
        pravo = PravoParser()
        for page in range(1, pravo_pages + 1):
            try:
                docs.extend(pravo.search(page=page))
            except Exception as exc:  # noqa: BLE001
                print(f"  !! pravo page {page}: {exc}")

    if government_limit:
        print(f"[npa] government rss {government_limit}")
        gov = GovernmentParser()
        try:
            rss = gov.fetch_rss(limit=government_limit)
            for stub in rss[:government_limit]:
                try:
                    docs.append(gov.fetch_article(stub.link) or stub)
                except Exception as exc:  # noqa: BLE001
                    print(f"  !! gov {stub.link}: {exc}")
                    docs.append(stub)
        except Exception as exc:  # noqa: BLE001
            print(f"  !! government rss: {exc}")

    inserted = 0
    with ParserDB() as db:
        sources = db.get_sources()
        for doc in docs:
            if not doc:
                continue
            article = doc.to_article() if hasattr(doc, "to_article") else None
            if not article:
                continue
            news_id = _insert_item(db, sources, article, source_url=article.get("link") or "")
            if not news_id:
                continue
            inserted += 1
            article["news_id"] = news_id
            report = link_one(
                article,
                store,
                model=model,
                dedup_news=True,
                skip_extract=True,
                embed_min_score=0.92,
            )
            n_ev = len(getattr(doc, "events", None) or article.get("npa_events") or [])
            print(
                f"  + {article.get('id_type') or '?'} {article.get('official_id') or ''} "
                f"events={n_ev} -> {report.get('action')} {report.get('object_id')}"
            )
    api.close()
    return inserted

def _rows_for_enrich(api: ApiDB) -> list[dict]:
    conn = api.connect()
    query = """
        SELECT n.id, n.source, n.title, n.url, n.author, n.category,
               n.text, n.description, s.name
        FROM news n
        LEFT JOIN sources s ON s.id = n.source_id
        WHERE NOT n.is_hidden
          AND COALESCE(n.text, '') <> ''
          AND COALESCE(n.description, '') = ''
          AND NOT EXISTS (
                SELECT 1
                FROM news sibling
                WHERE sibling.entity_id IS NOT NULL
                  AND sibling.entity_id = n.entity_id
                  AND sibling.id <> n.id
                  AND COALESCE(sibling.description, '') <> ''
          )
          AND (
                n.entity_id IS NULL
                OR n.id = (
                    SELECT MIN(x.id) FROM news x WHERE x.entity_id = n.entity_id
                )
          );
    """
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
    out = []
    for news_id, source, title, url, author, category, text, description, source_name in rows:
        out.append(
            {
                "news_id": news_id,
                "source": source_name or source,
                "title": title,
                "link": url,
                "author": author,
                "category": category,
                "text": text,
                "description": description,
            }
        )
    return out

def _rows_for_link(api: ApiDB) -> list[dict]:
    conn = api.connect()
    query = """
        SELECT n.id, n.source, n.title, n.url, n.author, n.category,
               n.text, n.description, s.name
        FROM news n
        LEFT JOIN sources s ON s.id = n.source_id
        WHERE NOT n.is_hidden
          AND n.entity_id IS NULL
          AND COALESCE(n.text, n.title, '') <> ''
        ORDER BY n.id;
    """
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
    out = []
    for news_id, source, title, url, author, category, text, description, source_name in rows:
        out.append(
            {
                "news_id": news_id,
                "source": source_name or source,
                "title": title,
                "link": url,
                "author": author,
                "category": category,
                "text": text,
                "description": description,
            }
        )
    return out

def link_unlinked(*, model: str) -> int:
    api = ApiDB()
    api.connect()
    api.ensure_schema()
    store = PostgresEntityStore(api)
    rows = _rows_for_link(api)
    print(f"[link] без entity_id: {len(rows)}")
    done = 0
    for i, row in enumerate(rows, 1):
        title = (row.get("title") or "")[:55]
        report = link_one(
            row,
            store,
            model=model,
            dedup_news=True,
            skip_extract=True,
        )
        action = report.get("action") or report.get("error") or "?"
        oid = report.get("object_id") or "—"
        print(f"  [{i}/{len(rows)}] {title} -> {action} | {oid}")
        if report.get("object_id"):
            done += 1
        store.save()
    api.close()
    return done

def apply_card(api: ApiDB, news_id: int, ui: dict, annotation: dict) -> None:
    rel = (annotation.get("relevance_to_company") or "").lower()
    in_general = rel in {"low", "medium", "high"}
    api.update_news(
        news_id,
        {
            "title": ui.get("title"),
            "description": ui.get("description"),
            "category": ui.get("category"),
            "importance": ui.get("importance"),
            "who": ui.get("who"),
            "what": ui.get("what"),
            "when": ui.get("when"),
            "consequences": ui.get("consequences"),
            "tags": ui.get("tags") or [],
            "in_general": in_general,
        },
    )

def enrich_db(*, model: str, concurrency: int) -> int:
    profile = load_company_profile()
    api = ApiDB()
    api.connect()
    rows = _rows_for_enrich(api)
    print(f"[llm] к разметке: {len(rows)} (модель {model}, workers={concurrency})")
    if not rows:
        return 0

    done = 0

    def task(row: dict) -> tuple[int, dict]:
        try:
            item = enrich_one(row, model=model, profile=profile)
            return row["news_id"], item
        except OpenRouterError as exc:
            return row["news_id"], {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return row["news_id"], {"error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=max(1, min(concurrency, len(rows)))) as pool:
        futs = {pool.submit(task, row): row for row in rows}
        for i, fut in enumerate(as_completed(futs), 1):
            news_id, item = fut.result()
            title = (futs[fut].get("title") or "")[:55]
            if "ui_card" not in item:
                print(f"  [{i}/{len(rows)}] {title} !! {item.get('error', '')[:80]}")
                continue
            ui = item["ui_card"]
            apply_card(api, news_id, ui, item["annotation"])
            done += 1
            print(
                f"  [{i}/{len(rows)}] {ui.get('title', '')[:55]} | "
                f"{ui.get('category')} / {ui.get('importance')} | "
                f"rel={ui.get('relevance_to_company')}"
            )
    api.close()
    return done

def report_npa_lifecycle() -> None:
    api = ApiDB()
    conn = api.connect()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT object_id, object_type, canonical_title,
                   COALESCE(jsonb_array_length(events), 0) AS n_events,
                   ids, events
            FROM entities
            WHERE object_type = 'npa'
            ORDER BY COALESCE(jsonb_array_length(events), 0) DESC, id
            """
        )
        rows = cur.fetchall()
    api.close()
    by_len = {}
    top = []
    for oid, otype, title, n_events, ids, events in rows:
        by_len[n_events] = by_len.get(n_events, 0) + 1
        if len(top) < 12:
            types = []
            for ev in events or []:
                types.append((ev or {}).get("event_type") or (ev or {}).get("stage") or "?")
            top.append(
                {
                    "object_id": oid,
                    "title": (title or "")[:120],
                    "n_events": n_events,
                    "ids": ids,
                    "event_types": types[:20],
                }
            )
    summary = {
        "npa_entities": len(rows),
        "with_2plus_events": sum(1 for _, _, _, n, _, _ in rows if n >= 2),
        "with_4plus_events": sum(1 for _, _, _, n, _, _ in rows if n >= 4),
        "event_count_hist": dict(sorted(by_len.items())),
        "longest": top,
    }
    out = ROOT / "ai" / "output" / "npa_lifecycle_stats.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== NPA lifecycle ===")
    print(f"сущностей НПА: {summary['npa_entities']}")
    print(f"с 2+ событиями: {summary['with_2plus_events']}")
    print(f"с 4+ событиями: {summary['with_4plus_events']}")
    print("гистограмма длины timeline:", summary["event_count_hist"])
    for item in top[:8]:
        print(f"  [{item['n_events']}] {item['title'][:70]}")
        print(f"      types={item['event_types'][:8]}")
    print(f"Report -> {out}")

def main() -> None:
    p = argparse.ArgumentParser(description="Сбор источников в БД и LLM-карточки для UI")
    p.add_argument("--per-source", type=int, default=4)
    p.add_argument("--delay", type=float, default=1.0)
    p.add_argument("--skip-web", action="store_true")
    p.add_argument("--skip-npa", action="store_true")
    p.add_argument("--skip-llm", action="store_true")
    p.add_argument("--skip-link", action="store_true")
    p.add_argument("--model", default=DEFAULT_CHAT_MODEL)
    p.add_argument("--concurrency", type=int, default=6)
    p.add_argument("--npa-regulation", type=int, default=8)
    p.add_argument("--npa-sozd", type=int, default=4)
    p.add_argument("--npa-gov", type=int, default=4)
    p.add_argument("--pravo-pages", type=int, default=0)
    args = p.parse_args()

    ApiDB().ensure_schema()

    if not args.skip_web:
        n = collect_web(per_source=args.per_source, delay=args.delay)
        print(f"Web: +{n}")
    if not args.skip_npa:
        n = collect_npa(
            regulation_limit=args.npa_regulation,
            sozd_limit=args.npa_sozd,
            government_limit=args.npa_gov,
            pravo_pages=args.pravo_pages,
            model=args.model,
        )
        print(f"NPA: +{n}")
        report_npa_lifecycle()
    if not args.skip_link:
        n = link_unlinked(model=args.model)
        print(f"Link: склеено {n}")
    if not args.skip_llm:
        n = enrich_db(model=args.model, concurrency=args.concurrency)
        print(f"LLM: размечено {n}")

if __name__ == "__main__":
    main()
