import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


from ai.daily_brief import generate_daily_briefs_all_models  # noqa: E402
from ai.enrich import enrich_batch  # noqa: E402
from ai.fetch_news import fetch_news, parse_since  # noqa: E402
from ai.openrouter import DEFAULT_MODELS, default_concurrency, list_models  # noqa: E402


def main() -> None:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Fetch + OpenRouter annotate news")
    parser.add_argument("--per-source", type=int, default=2, help="Статей с каждого RSS")
    parser.add_argument("--delay", type=float, default=1.0, help="Пауза между статьями (сек)")
    parser.add_argument(
        "--since",
        help="Фильтр pubDate >= since (yesterday | YYYY-MM-DD | ISO)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "ai" / "output",
    )
    parser.add_argument("--fetch-only", action="store_true", help="Только парсинг, без LLM")
    parser.add_argument(
        "--input",
        type=Path,
        help="Готовый raw_news.json вместо повторного парсинга",
    )
    parser.add_argument(
        "--models",
        nargs="*",
        help="Модели OpenRouter (по умолчанию из LLM_MODELS или deepseek/deepseek-v4-flash)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Обработать только первые N статей",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Параллельные запросы к LLM (LLM_CONCURRENCY из .env, default 4)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        help="Число параллельных LLM-запросов",
    )
    parser.add_argument(
        "--daily-brief",
        action="store_true",
        help="Сгенерировать daily brief (10 пунктов) вместо карточек",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="Показать модели по умолчанию и выйти",
    )
    args = parser.parse_args()

    if args.list_models:
        print("Модели по умолчанию (OpenRouter):")
        for m in list_models():
            print(f"  - {m}")
        print("\nПримеры других моделей OpenRouter:")
        for m in DEFAULT_MODELS:
            if m not in list_models():
                print(f"  - {m}")
        return

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    since_dt = parse_since(args.since) if args.since else None

    if args.input:
        articles = json.loads(args.input.read_text(encoding="utf-8"))
        print(f"Loaded {len(articles)} articles from {args.input}")
    else:
        print("Fetching news...")
        articles = fetch_news(
            per_source=args.per_source,
            delay=args.delay,
            since=since_dt,
            output_dir=output_dir,
        )
        print(f"Fetched {len(articles)} articles")

    articles = [a for a in articles if (a.get("text") or "").strip()]
    if args.limit:
        articles = articles[: args.limit]
    if not articles:
        print("No articles with extracted text. Check parsers / network.")
        sys.exit(1)
    print(f"Will process {len(articles)} articles with body text")

    if args.fetch_only:
        print("Done (--fetch-only).")
        return

    models = args.models or list_models()
    concurrency = args.concurrency or default_concurrency()
    print(f"Models: {', '.join(models)} | concurrency={concurrency}")

    if args.daily_brief:
        brief_day = since_dt.date() if since_dt else date.today()
        generate_daily_briefs_all_models(
            articles,
            models,
            day=brief_day,
            concurrency=concurrency,
            output_dir=output_dir,
        )
        print(f"\nDone. Daily briefs in {output_dir}/daily_brief_*.md")
        return

    enrich_batch(
        articles,
        models=models,
        output_dir=output_dir,
        concurrency=concurrency,
        parallel=args.parallel,
    )
    print("\nDone. See ai/output/ui_cards.json and annotated_*.json")

    ui_path = output_dir / "ui_cards.json"
    if ui_path.exists():
        from ai.preview_cards import card_to_markdown

        cards = json.loads(ui_path.read_text(encoding="utf-8"))
        preview_path = output_dir / "preview.md"
        preview_path.write_text(
            "# Превью карточек\n\n"
            + "\n---\n\n".join(card_to_markdown(c) for c in cards),
            encoding="utf-8",
        )
        print(f"Preview -> {preview_path}")


if __name__ == "__main__":
    main()
