import csv

from entity_extraction import EntityMatchResult, match_entities
from gazetteers import REGULATORY_CONTENT_MARKERS
from similarity import TfidfSimilarityScorer

DATASET_PATH: str = "/mnt/user-data/outputs/gs_labs_priority_dataset_v3.csv"


def is_regulatory_content(text: str) -> bool:
    text_lower: str = text.lower()
    return any(marker in text_lower for marker in REGULATORY_CONTENT_MARKERS)


def classify(score: float, is_reg: bool, competitor: bool, company: bool,
             high_thr: float, med_thr: float) -> str:
    if company:
        return "high"
    if is_reg and score >= med_thr:
        return "high"
    
    if competitor:
        return "medium"
    
    if score >= high_thr:
        return "high"
    
    if score >= med_thr:
        return "medium"
    
    return "low"


def main() -> None:
    scorer: TfidfSimilarityScorer = TfidfSimilarityScorer()

    with open(DATASET_PATH, encoding="utf-8") as f:
        rows: list[dict[str, str]] = list(csv.DictReader(f))

    cache: list[tuple[dict[str, str], EntityMatchResult, float, bool]] = []
    for row in rows:
        text: str = row["title"] + ". " + row["summary"]
        ent: EntityMatchResult = match_entities(text)
        score: float = max(scorer.score(text).values())
        cache.append((row, ent, score, is_regulatory_content(text)))

    print(f"{'HIGH':>6s} {'MEDIUM':>7s} {'accuracy':>10s}")
    results: list[tuple[float, float, int]] = []
    for high_thr in [i / 1000 for i in range(0, 300, 5)]:
        med_thr: float = high_thr / 2
        correct: int = sum(
            classify(score, is_reg, ent.competitor_mentioned, ent.company_mentioned,
                     high_thr, med_thr) == row["priority"]
            for row, ent, score, is_reg in cache
        )
        results.append((high_thr, med_thr, correct))

    best: tuple[float, float, int] = max(results, key=lambda r: r[2])
    print(f"Лучший результат: HIGH={best[0]:.3f} MEDIUM={best[1]:.3f} "
          f"accuracy={best[2]}/{len(rows)} = {best[2]/len(rows):.1%}\n")

    print("Плато вокруг лучшего результата (чтобы убедиться, что это не игла):")
    for high_thr, med_thr, correct in results:
        if correct >= best[2] - 1:
            marker: str = " <-- выбрано в priority_rules.py" if abs(high_thr - 0.02) < 1e-9 else ""
            print(f"  HIGH={high_thr:.3f} MEDIUM={med_thr:.3f}  {correct}/{len(rows)} = {correct/len(rows):.1%}{marker}")


if __name__ == "__main__":
    main()
