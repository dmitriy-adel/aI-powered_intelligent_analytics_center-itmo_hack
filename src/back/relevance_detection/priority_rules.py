from dataclasses import dataclass

from entity_extraction import EntityMatchResult, match_entities
from gazetteers import REGULATORS, REGULATORY_CONTENT_MARKERS
from similarity import SimilarityScorer, TfidfSimilarityScorer

SIMILARITY_HIGH_THRESHOLD: float = 0.02
SIMILARITY_MEDIUM_THRESHOLD: float = 0.01


@dataclass
class PriorityResult:
    priority: str  # "high" | "medium" | "low"
    reasons: list[str]
    entity_match: EntityMatchResult
    domain_scores: dict[str, float]
    max_domain_score: float
    is_regulator_source: bool


def _is_regulator_source(source: str) -> bool:
    if not source:
        return False
    source_lower: str = source.lower()
    return any(reg.lower() in source_lower for reg in REGULATORS)


def _is_regulatory_content(text: str) -> bool:
    text_lower: str = text.lower()
    return any(marker in text_lower for marker in REGULATORY_CONTENT_MARKERS)


def classify_priority(text: str, source: str = "", scorer: SimilarityScorer | None = None) -> PriorityResult:
    scorer = scorer or TfidfSimilarityScorer()

    entities: EntityMatchResult = match_entities(text)
    domain_scores: dict[str, float] = scorer.score(text)
    max_score: float = max(domain_scores.values()) if domain_scores else 0.0
    is_regulator: bool = _is_regulator_source(source) or _is_regulatory_content(text)

    reasons: list[str] = []

    if entities.company_mentioned:
        reasons.append(
            f"прямое упоминание компании/продукта: {', '.join(entities.matched_company_terms)}"
        )
        return PriorityResult("high", reasons, entities, domain_scores, max_score, is_regulator)

    if is_regulator and max_score >= SIMILARITY_MEDIUM_THRESHOLD:
        reasons.append(
            f"НПА/регуляторный контент, тема попадает в бизнес-домен (score={max_score:.3f})"
        )
        return PriorityResult("high", reasons, entities, domain_scores, max_score, is_regulator)

    if entities.competitor_mentioned:
        reasons.append(
            f"упоминание конкурента: {', '.join(entities.matched_competitor_terms)}"
        )
        return PriorityResult("medium", reasons, entities, domain_scores, max_score, is_regulator)

    if max_score >= SIMILARITY_HIGH_THRESHOLD:
        best_domain: str = max(domain_scores, key=domain_scores.get)
        reasons.append(
            f"высокая тематическая близость к направлению «{best_domain}» (score={max_score:.3f})"
        )
        return PriorityResult("high", reasons, entities, domain_scores, max_score, is_regulator)

    if max_score >= SIMILARITY_MEDIUM_THRESHOLD:
        best_domain = max(domain_scores, key=domain_scores.get)
        reasons.append(
            f"умеренная тематическая близость к направлению «{best_domain}» (score={max_score:.3f})"
        )
        return PriorityResult("medium", reasons, entities, domain_scores, max_score, is_regulator)

    reasons.append("нет совпадений с компанией, конкурентами или бизнес-доменами")
    return PriorityResult("low", reasons, entities, domain_scores, max_score, is_regulator)


if __name__ == "__main__":
    samples: list[tuple[str, str]] = [
        ("«Триколор» совместно с технологическим партнером GS Labs завершил "
         "тестирование системы условного доступа CAS Dreguard.", "TAdviser"),
        ("Правительство включило системы условного доступа в перечень объектов КИИ.", "Habr"),
        ("Российский разработчик IPTVPORTAL представил обновление платформы для операторов.", "telesputnik"),
        ("Прогноз погоды на сентябрь 2026 года в Москве.", "Lenta.ru"),
    ]
    scorer: TfidfSimilarityScorer = TfidfSimilarityScorer()
    for text, source in samples:
        result: PriorityResult = classify_priority(text, source, scorer)
        print(f"[{result.priority.upper()}] {text}")
        for r in result.reasons:
            print("   ", r)
        print()
