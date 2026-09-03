import argparse
import json
from pathlib import Path


def card_to_markdown(card: dict) -> str:
    lines = [
        f"## {card.get('title', '—')}",
        "",
        f"**Оригинальный заголовок:** {card.get('title_original', '—')}",
        f"**Источник:** {card.get('source_name', '—')} · **Категория:** {card.get('category')} · **Важность:** {card.get('importance')}",
        f"**Релевантность GS Labs:** {card.get('relevance_to_company', '—')}",
        "",
        card.get("description") or "",
        "",
        "| | |",
        "|---|---|",
        f"| **Кто** | {card.get('who', '—')} |",
        f"| **Что** | {card.get('what', '—')} |",
        f"| **Когда** | {card.get('when', '—')} |",
        f"| **Последствия** | {card.get('consequences', '—')} |",
        "",
        f"**Влияние на компанию:** {card.get('company_impact', '—')}",
        "",
    ]
    tags = card.get("tags") or []
    if tags:
        lines.append("**Теги:** " + ", ".join(f"`{t}`" for t in tags))
        lines.append("")

    excel = card.get("excel_row") or {}
    if excel:
        lines.append("**Excel-поля:**")
        for k, v in excel.items():
            lines.append(f"- {k}: {v}")
        lines.append("")

    lines.append(f"[Оригинал]({card.get('link', '#')})")
    lines.append("")
    return "\n".join(lines)


def main():
    here = Path(__file__).resolve().parent
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path, nargs="?", default=here / "output" / "ui_cards.json")
    p.add_argument("-o", "--output", type=Path, default=here / "output" / "preview.md")
    args = p.parse_args()

    cards = json.loads(args.input.read_text(encoding="utf-8"))
    md = "# Превью карточек\n\n" + "\n---\n\n".join(card_to_markdown(c) for c in cards)
    args.output.write_text(md, encoding="utf-8")
    print(f"Wrote {len(cards)} cards -> {args.output}")


if __name__ == "__main__":
    main()
