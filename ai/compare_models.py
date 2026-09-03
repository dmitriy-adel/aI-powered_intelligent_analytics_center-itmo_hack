import argparse
import json
from pathlib import Path


def _row(item: dict, key: str) -> str:
    if "error" in item:
        return f"ERROR: {item['error'][:80]}"
    ui = item.get("ui_card") or {}
    ann = item.get("annotation") or {}
    if key == "factual_title":
        return ui.get("title") or ann.get("factual_title") or "—"
    if key in ui:
        return str(ui[key])
    return str(ann.get(key, "—"))


def build_report(
    *,
    items_a: list[dict],
    items_b: list[dict],
    raw_samples: list[dict] | None,
    label_a: str,
    label_b: str,
    title: str,
) -> str:
    lines = [f"# {title}", ""]
    agree_rel = agree_imp = 0
    total_ms_a = total_ms_b = 0.0
    total_cost_a = total_cost_b = 0.0
    n = min(len(items_a), len(items_b))

    for i in range(n):
        a, b = items_a[i], items_b[i]
        raw = (raw_samples[i] if raw_samples and i < len(raw_samples) else {}) or {}
        meta = raw.get("excel_meta") or {}
        excel = {
            "sheet": raw.get("sheet"),
            "к1": meta.get("к1"),
            "категория": meta.get("итоговая_категория"),
            "стадия": meta.get("стадия"),
        }
        title_src = (raw.get("title") or a.get("raw", {}).get("title") or f"#{i+1}")[:80]

        lines.append(f"## {i + 1}. [{excel.get('sheet', '?')}] {title_src}")
        if excel.get("категория"):
            lines.append(
                f"*Excel-эталон:* К1={excel.get('к1')}, категория **{excel.get('категория')}**"
            )
        lines.append("")
        lines.append(f"| | {label_a} | {label_b} |")
        lines.append("|---|---|---|")
        lines.append(f"| **factual_title** | {_row(a, 'factual_title')} | {_row(b, 'factual_title')} |")
        lines.append(f"| relevance | {_row(a, 'relevance_to_company')} | {_row(b, 'relevance_to_company')} |")
        lines.append(f"| importance | {_row(a, 'importance')} | {_row(b, 'importance')} |")
        lines.append(f"| category | {_row(a, 'category')} | {_row(b, 'category')} |")

        lat_a = (a.get("meta") or {}).get("latency_ms")
        lat_b = (b.get("meta") or {}).get("latency_ms")
        if lat_a:
            total_ms_a += lat_a
        if lat_b:
            total_ms_b += lat_b
        ca = (a.get("meta") or {}).get("cost")
        cb = (b.get("meta") or {}).get("cost")
        if isinstance(ca, (int, float)):
            total_cost_a += ca
        if isinstance(cb, (int, float)):
            total_cost_b += cb
        ca_s = f"${ca:.6f}" if isinstance(ca, (int, float)) else "—"
        cb_s = f"${cb:.6f}" if isinstance(cb, (int, float)) else "—"
        lines.append(f"| latency | {lat_a or '—'}ms | {lat_b or '—'}ms |")
        lines.append(f"| cost | {ca_s} | {cb_s} |")
        lines.append("")

        ra = _row(a, "relevance_to_company")
        rb = _row(b, "relevance_to_company")
        ia = _row(a, "importance")
        ib = _row(b, "importance")
        if ra == rb:
            agree_rel += 1
        if ia == ib:
            agree_imp += 1

    if n:
        lines.append("## Итого")
        lines.append(f"- **{label_a}:** {total_ms_a/1000:.1f}s, ${total_cost_a:.6f} за {n} статей")
        lines.append(f"- **{label_b}:** {total_ms_b/1000:.1f}s, ${total_cost_b:.6f} за {n} статей")
        lines.append(f"- Согласованность relevance: {agree_rel}/{n} ({100*agree_rel/n:.0f}%)")
        lines.append(f"- Согласованность importance: {agree_imp}/{n} ({100*agree_imp/n:.0f}%)")

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", type=Path, required=True)
    parser.add_argument("--b", type=Path, required=True)
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--label-a", default="20b")
    parser.add_argument("--label-b", default="120b")
    parser.add_argument("--title", default="Сравнение моделей")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    raw = json.loads(args.raw.read_text(encoding="utf-8")) if args.raw else None
    report = build_report(
        items_a=json.loads(args.a.read_text(encoding="utf-8")),
        items_b=json.loads(args.b.read_text(encoding="utf-8")),
        raw_samples=raw,
        label_a=args.label_a,
        label_b=args.label_b,
        title=args.title,
    )
    args.out.write_text(report, encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
