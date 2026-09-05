from __future__ import annotations

from dataclasses import dataclass, field

from priority_rules import PriorityResult, SIMILARITY_HIGH_THRESHOLD, classify_priority
from similarity import SimilarityScorer, TfidfSimilarityScorer


@dataclass
class RelevanceResult:
    relevance: str  # "high" | "medium" | "low"
    score: float    # уверенность, 0..1
    reasons: list[str] = field(default_factory=list)
    details: PriorityResult | None = None


class RelevanceDetector:

    def __init__(self, scorer: SimilarityScorer | None = None) -> None:
        self._scorer: SimilarityScorer = scorer or TfidfSimilarityScorer()

    def detect(self, source: str, title: str, text: str) -> RelevanceResult:
        full_text: str = f"{title}. {text}" if title else text
        result: PriorityResult = classify_priority(full_text, source=source, scorer=self._scorer)
        score: float = self._compute_score(result)
        return RelevanceResult(
            relevance=result.priority,
            score=score,
            reasons=result.reasons,
            details=result,
        )

    def detect_batch(self, items: list[dict[str, str]]) -> list[RelevanceResult]:
        return [
            self.detect(item.get("source", ""), item.get("title", ""), item.get("text", ""))
            for item in items
        ]

    def _compute_score(self, result: PriorityResult) -> float:
        entity = result.entity_match

        if entity.company_mentioned:
            return 1.0

        if result.is_regulator_source and result.priority == "high":
            return 0.9

        if entity.competitor_mentioned:
            return 0.6

        domain_component: float = 0.0
        if SIMILARITY_HIGH_THRESHOLD:
            domain_component = min(1.0, result.max_domain_score / SIMILARITY_HIGH_THRESHOLD)
            
        return round(domain_component, 3)

    def __repr__(self) -> str:
        return f"RelevanceDetector(scorer={type(self._scorer).__name__})"


if __name__ == "__main__":
    detector: RelevanceDetector = RelevanceDetector()

    samples: list[tuple[str, str, str]] = [
        ("TAdviser", "«Триколор» завершил тестирование новой системы условного доступа",
         "GS Labs совместно с «Триколором» завершила тестирование CAS Dreguard 6-го поколения"),
        ("Habr", "Правительство включило системы условного доступа в перечень объектов КИИ",
         "Распоряжение №360-р признаёт CAS-решения критической информационной инфраструктурой"),
        ("telesputnik", "IPTVPORTAL представил обновление платформы",
         "Российский разработчик CAS обновил платформу для операторов IPTV"),
        ("Lenta.ru", "Прогноз погоды на сентябрь 2026 года в Москве",
         "Похолодание и дожди ожидаются в столичном регионе на следующей неделе"),
    ]

    for source, title, text in samples:
        r: RelevanceResult = detector.detect(source, title, text)
        print(f"[{r.relevance.upper():6s} score={r.score:.2f}] {title}")
        for reason in r.reasons:
            print("   ", reason)
            
        print()
