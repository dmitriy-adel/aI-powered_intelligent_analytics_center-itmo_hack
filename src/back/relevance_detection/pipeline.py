import csv
import sys

from priority_rules import PriorityResult, classify_priority
from similarity import TfidfSimilarityScorer


def run(input_path: str, output_path: str) -> None:
    scorer: TfidfSimilarityScorer = TfidfSimilarityScorer()

    with open(input_path, encoding="utf-8") as f:
        rows: list[dict[str, str]] = list(csv.DictReader(f))

    fieldnames: list[str] = list(rows[0].keys()) + ["priority", "priority_reasons"]

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            text: str = f"{row.get('title', '')}. {row.get('summary', '')}"
            result: PriorityResult = classify_priority(text, source=row.get("source", ""), scorer=scorer)
            row["priority"] = result.priority
            row["priority_reasons"] = " | ".join(result.reasons)
            writer.writerow(row)

    print(f"Готово: {len(rows)} новостей размечено -> {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Использование: python3 pipeline.py input.csv output.csv")
        sys.exit(1)

    run(sys.argv[1], sys.argv[2])
