import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai.enrich import enrich_one, load_company_profile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "ai" / "output" / "excel_sample_10.json")
    parser.add_argument("--model", default="openai/gpt-oss-20b")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--delay", type=float, default=2.0)
    args = parser.parse_args()

    articles = json.loads(args.input.read_text(encoding="utf-8"))
    safe = args.model.replace("/", "_").replace(":", "_")
    out_path = args.out or (ROOT / "ai" / "output" / f"excel_annotated_{safe}.json")

    if out_path.exists():
        results = json.loads(out_path.read_text(encoding="utf-8"))
    else:
        results = []

    profile = load_company_profile()
    start = len(results)
    print(f"Resume from {start}/{len(articles)} -> {out_path}")

    for idx in range(start, len(articles)):
        article = articles[idx]
        title = (article.get("title") or "")[:70]
        print(f"[{idx + 1}/{len(articles)}] {title}")
        try:
            item = enrich_one(article, model=args.model, profile=profile)
            results.append(item)
            ui = item["ui_card"]
            print(
                f"  -> {ui['title'][:70]} | {ui['category']} / {ui['importance']} | "
                f"rel={ui['relevance_to_company']} | {item['meta']['latency_ms']}ms"
            )
        except Exception as exc:
            print(f"  !! {exc}")
            results.append({"raw": {"title": article.get("title")}, "error": str(exc)})

        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        if idx + 1 < len(articles):
            time.sleep(args.delay)

    ui_cards = [r["ui_card"] for r in results if "ui_card" in r]
    ui_path = ROOT / "ai" / "output" / f"excel_ui_cards_{safe}.json"
    ui_path.write_text(json.dumps(ui_cards, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Done: {len(ui_cards)} cards -> {out_path}")


if __name__ == "__main__":
    main()
