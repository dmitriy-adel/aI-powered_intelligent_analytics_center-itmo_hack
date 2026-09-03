import json
from datetime import date
from pathlib import Path
from typing import Any, Optional


from ai.openrouter import OpenRouterError, complete_text, map_parallel


DAILY_BRIEF_SYSTEM = """
Ты аналитик мониторинга для GS Labs (ООО "Цифра") — разработчика ПО для цифрового ТВ, OTT, CAS/DRM.


Задача: составить executive brief за день для PR/GR-специалиста, принимающего решения.


Правила:
1. Ровно 10 пунктов — самое важное за день для компании и отрасли (телеком, медиа, IT-регулирование).
2. Каждый пункт: 1–2 предложения, конкретно (кто / что / зачем), без воды и кликбейта.
3. Приоритет: регуляторика, НПА, рынок OTT/ТВ, CAS/DRM, реестр ПО, КИИ — выше общих политических новостей.
4. Если материалов мало — честно укажи в preamble и заполни пункты тем, что есть.
5. Формат markdown: заголовок, дата, затем нумерованный список 1–10.
6. Язык: русский.
"""




def _snippet(article: dict, max_chars: int = 180) -> str:
   text = (article.get("text") or article.get("description") or "").strip()
   if len(text) > max_chars:
       text = text[:max_chars] + "…"
   return text




def build_daily_brief_prompt(
   articles: list[dict],
   *,
   day: date,
   max_articles: int = 35,
   compact: bool = False,
) -> str:
   subset = articles[:max_articles]
   lines = [
       f"Дата брифа: {day.isoformat()}",
       f"Материалов в ленте: {len(articles)} (в промпт: {len(subset)})",
       "",
       "ИСТОЧНИКИ ЗА ДЕНЬ:",
   ]
   for i, a in enumerate(subset, 1):
       if compact:
           lines.append(
               f"[{i}] {a.get('source', '—')} | {a.get('title', '—')} | {a.get('link', '—')}"
           )
       else:
           lines.append(
               f"\n--- [{i}] {a.get('source', '—')} | {a.get('title', '—')}\n"
               f"URL: {a.get('link', '—')}\n"
               f"Дата: {a.get('pub_date', '—')}\n"
               f"{_snippet(a)}"
           )
   lines.append(
       "\n\nСоставь daily brief: 10 пунктов «что произошло за день», "
       "ориентируясь на релевантность для GS Labs."
   )
   return "\n".join(lines)




def generate_daily_brief(
   articles: list[dict],
   *,
   model: str,
   day: Optional[date] = None,
) -> dict[str, Any]:
   day = day or date.today()
   prompt = build_daily_brief_prompt(articles, day=day, max_articles=35)
   max_tokens = 4096
   try:
       result = complete_text(
           model=model,
           system_prompt=DAILY_BRIEF_SYSTEM,
           user_prompt=prompt,
           temperature=0.3,
           max_tokens=max_tokens,
       )
       return {
           "model": result["model"],
           "day": day.isoformat(),
           "articles_count": len(articles),
           "brief": result["content"],
           "meta": {
               "latency_ms": result["latency_ms"],
               "usage": result["usage"],
               "cost": result.get("cost"),
           },
       }
   except OpenRouterError as exc:
       return {"model": model, "day": day.isoformat(), "error": str(exc)}




def generate_daily_briefs_all_models(
   articles: list[dict],
   models: list[str],
   *,
   day: Optional[date] = None,
   concurrency: int = 3,
   output_dir: Optional[Path] = None,
) -> dict[str, dict]:
   day = day or date.today()


   def run(model: str) -> tuple[str, dict]:
       print(f"  brief -> {model}")
       return model, generate_daily_brief(articles, model=model, day=day)


   pairs = map_parallel(models, run, concurrency=concurrency, label="briefs")
   by_model = {m: r for m, r in pairs}


   if output_dir:
       output_dir.mkdir(parents=True, exist_ok=True)
       safe_day = day.isoformat()
       for model, item in by_model.items():
           safe = model.replace("/", "_").replace(":", "_")
           path = output_dir / f"daily_brief_{safe_day}_{safe}.md"
           if "brief" in item:
               header = f"# Daily brief {safe_day}\n\n**Model:** {model}\n**Articles:** {len(articles)}\n\n"
               path.write_text(header + item["brief"], encoding="utf-8")
           else:
               path.write_text(f"# Error\n\n{item.get('error')}", encoding="utf-8")
       summary_path = output_dir / f"daily_brief_{safe_day}_all.json"
       summary_path.write_text(json.dumps(by_model, ensure_ascii=False, indent=2), encoding="utf-8")
       print(f"Saved briefs -> {output_dir}")


   return by_model




