import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.embed import embed_texts
from ai.openrouter import DEFAULT_CHAT_MODEL, OpenRouterError, complete_json, list_models
from ai.prompts_npa import (
    EXTRACT_SYSTEM,
    JUDGE_NEWS_SYSTEM,
    JUDGE_SYSTEM,
    build_extract_prompt,
    build_judge_prompt,
)
from ai.regulatory_store import (
    RegulatoryStore,
    canonical_embed_text,
    has_strong_id,
    ids_from_article,
    merge_ids,
)
from ai.schema_npa import EXTRACT_SCHEMA, JUDGE_SCHEMA

DEFAULT_EMBED_MIN_SCORE = 0.60
DEFAULT_EMBED_AUTO_SAME = 0.75

def _as_article(item: dict) -> dict:
    if "raw" in item and isinstance(item["raw"], dict):
        raw = dict(item["raw"])
        if item.get("annotation"):
            raw["_annotation"] = item["annotation"]
        return raw
    return item

def _without_embedding(obj: dict) -> dict:
    slim = dict(obj)
    slim.pop("embedding", None)
    return slim

def extract_mention(article: dict, *, model: str) -> dict[str, Any]:
    result = complete_json(
        model=model,
        system_prompt=EXTRACT_SYSTEM,
        user_prompt=build_extract_prompt(article),
        schema=EXTRACT_SCHEMA,
        schema_name="npa_extract",
    )
    parsed = result["json"]
    parsed.setdefault("ids", {})
    return {
        "extract": parsed,
        "meta": {
            "model": result["model"],
            "latency_ms": result["latency_ms"],
            "cost": result.get("cost"),
        },
    }

def _partition_neighbours(
    neighbours: list[tuple[dict, float]],
    *,
    min_score: float,
    auto_same: float,
) -> tuple[list[tuple[dict, float]], list[tuple[dict, float]], list[tuple[dict, float]]]:
    """Разложить knn: слишком близко / спорная зона / слишком далеко."""
    auto: list[tuple[dict, float]] = []
    band: list[tuple[dict, float]] = []
    skipped: list[tuple[dict, float]] = []
    for obj, score in neighbours:
        if score >= auto_same:
            auto.append((obj, score))
        elif score >= min_score:
            band.append((obj, score))
        else:
            skipped.append((obj, score))
    return auto, band, skipped

def judge_candidates(
    extract: dict,
    candidates: list[dict],
    *,
    model: str,
    object_type: str = "npa",
) -> list[dict]:
    """LLM same/different только по спорным кандидатам (середина cosine)."""
    if not candidates:
        return []
    system = JUDGE_NEWS_SYSTEM if object_type == "news_plot" else JUDGE_SYSTEM
    result = complete_json(
        model=model,
        system_prompt=system,
        user_prompt=build_judge_prompt(extract, candidates, object_type=object_type),
        schema=JUDGE_SCHEMA,
        schema_name="npa_judge",
    )
    payload = result.get("json")
    if isinstance(payload, list):
        verdicts = payload
    elif isinstance(payload, dict):
        verdicts = payload.get("verdicts") or []
    else:
        verdicts = []
    by_id = {v.get("object_id"): v for v in verdicts if v.get("object_id")}
    out = []
    for obj in candidates:
        oid = obj.get("object_id")
        hit = by_id.get(oid) or {"object_id": oid, "verdict": "different", "reason": "не вернул судья"}
        out.append(hit)
    return out

def _timeline_events(article: dict, extract: dict) -> list[dict]:
    """Паспорт НПА уже содержит RSS/стадии — это и есть цикл, не одна карточка."""
    publication = _event_from(article, extract)
    extra: list[dict] = []
    for ev in article.get("npa_events") or []:
        extra.append(
            {
                "source": ev.get("source") or article.get("source"),
                "title": ev.get("title") or ev.get("stage") or article.get("title"),
                "link": ev.get("link") or article.get("link"),
                "date": ev.get("date"),
                "event_type": ev.get("event_type") or "stage",
                "summary": ev.get("summary"),
                "stage": ev.get("stage") or ev.get("title"),
                "object_title": extract.get("title") or article.get("title"),
                "news_id": article.get("news_id"),
            }
        )
    if extra:
        return extra
    return [publication]

def _event_from(article: dict, extract: dict) -> dict:
    return {
        "source": article.get("source"),
        "title": extract.get("description") or article.get("title"),
        "link": article.get("link"),
        "date": article.get("pub_date") or datetime.now(timezone.utc).isoformat(),
        "event_type": extract.get("event_type") or "other",
        "summary": extract.get("description"),
        "stage": extract.get("stage"),
        "object_title": extract.get("title") or article.get("title"),
        "news_id": article.get("news_id"),
    }

def _extract_without_llm(article: dict, source_ids: dict) -> dict[str, Any]:
    is_reg = has_strong_id(source_ids) or bool(article.get("official_id"))
    extract = {
        "is_regulatory": is_reg,
        "title": article.get("title") or "",
        "agency": article.get("department") or article.get("author") or "",
        "kind": article.get("kind") or "",
        "description": (article.get("summary") or article.get("text") or article.get("description") or "")[:400],
        "ids": {},
        "event_type": "published" if is_reg else "media_mention",
    }
    return {
        "extract": extract,
        "meta": {"model": "skip_extract", "latency_ms": 0, "cost": None},
    }

def link_one(
    article: dict,
    store: RegulatoryStore,
    *,
    model: str,
    top_k: int = 5,
    dedup_news: bool = False,
    embed_min_score: float = DEFAULT_EMBED_MIN_SCORE,
    embed_auto_same: float = DEFAULT_EMBED_AUTO_SAME,
    skip_extract: bool = False,
) -> dict[str, Any]:
    article = _as_article(article)
    source_ids = ids_from_article(article)

    if skip_extract:
        extracted = _extract_without_llm(article, source_ids)
    else:
        try:
            extracted = extract_mention(article, model=model)
        except OpenRouterError as exc:
            return {"link": article.get("link"), "error": str(exc)}

    extract = extracted["extract"]
    llm_ids = extract.get("ids") or {}
    ids = merge_ids(source_ids, llm_ids)
    is_reg = bool(extract.get("is_regulatory")) or has_strong_id(ids)
    object_type = "npa" if is_reg else ("news_plot" if dedup_news else "skip")

    extra = f"{article.get('title') or ''} {(article.get('text') or article.get('description') or '')[:500]}"
    embed_text = canonical_embed_text(extract, ids, extra)
    vectors, embed_method = embed_texts([embed_text])
    vector = vectors[0] if vectors else []
    timeline = _timeline_events(article, extract)
    event = timeline[0] if timeline else _event_from(article, extract)
    extra_events = timeline[1:]

    record: dict[str, Any] = {
        "publication": {
            "title": article.get("title"),
            "link": article.get("link"),
            "source": article.get("source"),
        },
        "extract": extract,
        "ids": ids,
        "embed_method": embed_method,
        "extract_meta": extracted["meta"],
        "object_type": object_type,
    }

    if object_type == "skip":
        record["action"] = "skip_non_regulatory"
        return record

    # 3. Точный match по официальному ID
    if object_type == "npa" and any(ids.values()):
        exact = store.find_by_ids(ids)
        if exact:
            store.attach(exact, ids=ids, event=event, embedding=vector)
            for ev in extra_events:
                store.attach(exact, ids=ids, event=ev)
            record["action"] = "exact_id"
            record["object_id"] = exact["object_id"]
            return record

    # 4–6. Embedding + пороги: auto-same / спорная зона (LLM) / слишком далеко
    neighbours = store.knn(vector, k=top_k, object_type=object_type) if vector else []
    record["neighbors"] = [
        {"object_id": obj["object_id"], "score": round(score, 4), "title": obj.get("canonical_title")}
        for obj, score in neighbours
    ]

    # Для НПА автосклейка опаснее: чужой ФЗ/ПП. Там только min-порог + LLM.
    effective_auto = embed_auto_same if object_type == "news_plot" else 2.0
    auto, band, skipped = _partition_neighbours(
        neighbours, min_score=embed_min_score, auto_same=effective_auto
    )
    record["embed_thresholds"] = {
        "min_score": embed_min_score,
        "auto_same": effective_auto,
    }
    record["skipped_below_threshold"] = [
        {"object_id": obj["object_id"], "score": round(score, 4)}
        for obj, score in skipped
    ]

    if auto:
        obj, score = auto[0]
        store.attach(obj, ids=ids, event=event, embedding=vector)
        for ev in extra_events:
            store.attach(obj, ids=ids, event=ev)
        record["action"] = "embed_same"
        record["object_id"] = obj["object_id"]
        record["embed_score"] = round(score, 4)
        return record

    if band:
        slim = [_without_embedding(obj) for obj, _ in band]
        try:
            judge_extract = dict(extract)
            if object_type == "news_plot":
                judge_extract["title"] = extract.get("title") or article.get("title") or ""
                judge_extract["description"] = (
                    extract.get("description")
                    or extract.get("summary")
                    or (article.get("text") or article.get("description") or "")[:400]
                )
            verdicts = judge_candidates(
                judge_extract, slim, model=model, object_type=object_type
            )
        except OpenRouterError as exc:
            record["action"] = "judge_failed_create"
            record["error"] = str(exc)
            obj = store.create(
                extract=extract,
                ids=ids,
                embedding=vector,
                event=event,
                object_type=object_type,
                extra_events=extra_events,
            )
            record["object_id"] = obj["object_id"]
            return record

        record["verdicts"] = verdicts
        same_ids = {v["object_id"] for v in verdicts if v.get("verdict") == "same"}
        same_ranked = [(obj, score) for obj, score in band if obj["object_id"] in same_ids]

        if len(same_ranked) == 1:
            obj, _ = same_ranked[0]
            store.attach(obj, ids=ids, event=event, embedding=vector)
            for ev in extra_events:
                store.attach(obj, ids=ids, event=ev)
            record["action"] = "llm_same"
            record["object_id"] = obj["object_id"]
            return record

        if len(same_ranked) > 1:
            obj, _ = same_ranked[0]
            store.attach(obj, ids=ids, event=event, embedding=vector)
            for ev in extra_events:
                store.attach(obj, ids=ids, event=ev)
            record["action"] = "llm_same_ambiguous"
            record["object_id"] = obj["object_id"]
            record["also_same"] = [o["object_id"] for o, _ in same_ranked[1:]]
            return record

    # 7. Никого не нашли — новый объект
    obj = store.create(
        extract=extract,
        ids=ids,
        embedding=vector,
        event=event,
        object_type=object_type,
        extra_events=extra_events,
    )
    record["action"] = "created"
    record["object_id"] = obj["object_id"]
    return record

def link_batch(
    articles: list[dict],
    store: RegulatoryStore,
    *,
    model: str,
    top_k: int = 5,
    dedup_news: bool = False,
    embed_min_score: float = DEFAULT_EMBED_MIN_SCORE,
    embed_auto_same: float = DEFAULT_EMBED_AUTO_SAME,
    skip_extract: bool = False,
) -> list[dict]:
    reports = []
    for i, article in enumerate(articles, 1):
        title = (_as_article(article).get("title") or "")[:60]
        print(f"[{i}/{len(articles)}] {title}")
        report = link_one(
            article,
            store,
            model=model,
            top_k=top_k,
            dedup_news=dedup_news,
            embed_min_score=embed_min_score,
            embed_auto_same=embed_auto_same,
            skip_extract=skip_extract,
        )
        reports.append(report)
        action = report.get("action")
        oid = report.get("object_id") or "—"
        print(f"  -> {action} | {oid}")
        store.save()
    return reports

def main() -> None:
    p = argparse.ArgumentParser(description="Link publications to regulatory objects")
    p.add_argument("--input", type=Path, required=True, help="JSON список публикаций / NPA-документов")
    p.add_argument(
        "--store",
        type=Path,
        default=ROOT / "ai" / "output" / "regulatory_objects.json",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=ROOT / "ai" / "output" / "npa_link_report.json",
    )
    p.add_argument("--model", default=None)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument(
        "--embed-min-score",
        type=float,
        default=DEFAULT_EMBED_MIN_SCORE,
        help="Ниже порога не считаем кандидатом и в LLM не отправляем",
    )
    p.add_argument(
        "--embed-auto-same",
        type=float,
        default=DEFAULT_EMBED_AUTO_SAME,
        help="Не ниже порога — сразу same без LLM. 1.0 отключает автосклейку",
    )
    p.add_argument(
        "--dedup-news",
        action="store_true",
        help="Нерегуляторные публикации тоже склеивать в сюжеты тем же knn+LLM",
    )
    p.add_argument(
        "--postgres",
        action="store_true",
        help="Писать сущности и эмбеды в таблицу entities, а не в JSON",
    )
    p.add_argument(
        "--skip-extract",
        action="store_true",
        help="Не звать LLM extract: тип npa/сюжет по official_id и regex",
    )
    args = p.parse_args()

    items = json.loads(args.input.read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("items") or items.get("objects") or [items]
    model = args.model or (list_models()[0] if list_models() else DEFAULT_CHAT_MODEL)
    if args.postgres:
        sys.path.insert(0, str(ROOT / "src" / "back"))
        from db_connection import DBConnection as ApiDB  # noqa: E402
        from ai.entity_store import PostgresEntityStore

        api = ApiDB()
        api.connect()
        store = PostgresEntityStore(api)
        store_label = "postgres:entities"
    else:
        store = RegulatoryStore(args.store)
        store_label = str(args.store)
    print(
        f"Store {store_label} ({len(store.objects)} objects) | model={model} | "
        f"min={args.embed_min_score} auto_same={args.embed_auto_same}"
    )

    reports = link_batch(
        items,
        store,
        model=model,
        top_k=args.top_k,
        dedup_news=args.dedup_news,
        embed_min_score=args.embed_min_score,
        embed_auto_same=args.embed_auto_same,
        skip_extract=args.skip_extract,
    )
    args.report.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    store.save()

    actions: dict[str, int] = {}
    for r in reports:
        actions[r.get("action") or "error"] = actions.get(r.get("action") or "error", 0) + 1
    print(f"\nObjects: {len(store.objects)} -> {store_label}")
    print(f"Report -> {args.report}")
    print("Actions:", actions)

if __name__ == "__main__":
    main()
