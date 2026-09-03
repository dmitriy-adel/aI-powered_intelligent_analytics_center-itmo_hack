import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional
import time


from ai.openrouter import OpenRouterError, annotate_article, default_concurrency, list_models
from ai.prompts import SYSTEM_PROMPT, build_user_prompt


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = Path(__file__).resolve().parent / "company_profile.json"




def load_company_profile() -> dict:
   return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))




def to_ui_card(raw: dict, annotation: dict, *, model: str) -> dict:
   """Поля, которые понимает текущий фронт (store.js / app.js)."""
   excel = annotation.get("excel") or {}
   return {
       "source": raw.get("source"),
       "source_name": raw.get("source"),
       "title": annotation.get("factual_title") or raw.get("title"),
       "title_original": raw.get("title"),
       "link": raw.get("link"),
       "author": raw.get("author") or "—",
       "category": annotation.get("category") or "Экономика",
       "importance": annotation.get("importance") or "Средний",
       "description": annotation.get("summary") or raw.get("description") or "",
       "pub_date": raw.get("pub_date") or "—",
       "who": annotation.get("who"),
       "what": annotation.get("what"),
       "when": annotation.get("when"),
       "consequences": annotation.get("consequences"),
       "tags": annotation.get("tags") or [],
       "document_type": annotation.get("document_type"),
       "relevance_to_company": annotation.get("relevance_to_company"),
       "company_impact": annotation.get("company_impact"),
       "evidence": annotation.get("evidence") or [],
       "excel_row": {
           "Тип документа": annotation.get("document_type"),
           "Стадия": excel.get("stage") or "—",
           "Суть / содержание": excel.get("essence"),
           "К1 Применимость (0-3)": excel.get("applicability_score"),
           "К6/Н1 Срочность (0-3)": excel.get("urgency_score"),
           "Н3 Масштаб (0-3)": excel.get("relevance_score"),
           "Категория актуальности": excel.get("actuality_category"),
       },
       "_llm_model": model,
       "_text_source": raw.get("_text_source"),
   }




def enrich_one(raw: dict, *, model: str, profile: dict | None = None) -> dict[str, Any]:
   profile = profile or load_company_profile()
   user_prompt = build_user_prompt(raw, profile)
   timeout = 300.0 if "120b" in model else 120.0
   result = annotate_article(
       model=model,
       system_prompt=SYSTEM_PROMPT,
       user_prompt=user_prompt,
       timeout=timeout,
   )
   ann = result["annotation"]
   return {
       "raw": {
           "source": raw.get("source"),
           "title": raw.get("title"),
           "link": raw.get("link"),
           "pub_date": raw.get("pub_date"),
           "excel_no": raw.get("excel_no"),
           "_text_source": raw.get("_text_source"),
       },
       "ui_card": to_ui_card(raw, ann, model=model),
       "annotation": ann,
       "meta": {
           "model": result["model"],
           "latency_ms": result["latency_ms"],
           "usage": result["usage"],
           "cost": result.get("cost"),
       },
   }




def _enrich_one_safe(article: dict, *, model: str, profile: dict) -> dict[str, Any]:
   try:
       return enrich_one(article, model=model, profile=profile)
   except OpenRouterError as exc:
       return {
           "raw": {"title": article.get("title"), "link": article.get("link")},
           "error": str(exc),
       }
   except Exception as exc:  # noqa: BLE001
       return {
           "raw": {"title": article.get("title"), "link": article.get("link")},
           "error": f"{type(exc).__name__}: {exc}",
       }




def enrich_batch(
   articles: list[dict],
   *,
   models: list[str] | None = None,
   output_dir: Path | None = None,
   concurrency: int | None = None,
   parallel: bool = False,
) -> dict[str, list[dict]]:
   models = models or list_models()
   profile = load_company_profile()
   workers = concurrency or default_concurrency()
   results_by_model: dict[str, list[dict]] = {m: [] for m in models}


   for model in models:
       print(f"\n=== Model: {model} (workers={workers if parallel else 1}) ===")


       if parallel and len(articles) > 1:
           indexed = list(enumerate(articles))


           def task(pair: tuple[int, dict]) -> tuple[int, dict]:
               idx, article = pair
               item = _enrich_one_safe(article, model=model, profile=profile)
               return idx, item


           with ThreadPoolExecutor(max_workers=min(workers, len(articles))) as pool:
               future_map = {pool.submit(task, p): p[0] for p in indexed}
               bucket: list[Optional[dict]] = [None] * len(articles)
               done = 0
               for fut in as_completed(future_map):
                   idx, item = fut.result()
                   bucket[idx] = item
                   done += 1
                   title = (articles[idx].get("title") or "")[:50]
                   if "ui_card" in item:
                       ui = item["ui_card"]
                       print(
                           f"  [{done}/{len(articles)}] {title} -> "
                           f"rel={ui['relevance_to_company']} | {item['meta']['latency_ms']}ms"
                       )
                   else:
                       print(f"  [{done}/{len(articles)}] {title} !! {item.get('error', '')[:60]}")
           results_by_model[model] = [b for b in bucket if b is not None]
       else:
           for idx, article in enumerate(articles, 1):
               title_preview = (article.get("title") or "")[:70]
               print(f"[{idx}/{len(articles)}] {title_preview}")
               item = _enrich_one_safe(article, model=model, profile=profile)
               results_by_model[model].append(item)
               if "ui_card" in item:
                   ui = item["ui_card"]
                   print(
                       f"  -> {ui['title'][:70]} | "
                       f"{ui['category']} / {ui['importance']} | "
                       f"rel={ui['relevance_to_company']} | "
                       f"{item['meta']['latency_ms']}ms"
                   )
               else:
                   print(f"  !! {item.get('error', '')[:120]}")
               if idx < len(articles):
                   time.sleep(1)


   if output_dir:
       output_dir.mkdir(parents=True, exist_ok=True)
       for model, items in results_by_model.items():
           safe = model.replace("/", "_").replace(":", "_")
           path = output_dir / f"annotated_{safe}.json"
           path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
           print(f"Saved -> {path}")


       ui_cards = []
       for i in range(len(articles)):
           for model in models:
               bucket = results_by_model.get(model, [])
               if i < len(bucket) and "ui_card" in bucket[i]:
                   ui_cards.append(bucket[i]["ui_card"])
                   break
       if ui_cards:
           ui_path = output_dir / "ui_cards.json"
           ui_path.write_text(json.dumps(ui_cards, ensure_ascii=False, indent=2), encoding="utf-8")
           print(f"Saved UI cards -> {ui_path}")
       else:
           print("No UI cards produced — ui_cards.json not overwritten")


   return results_by_model




