from dataclasses import dataclass, field

from natasha import Segmenter, NewsEmbedding, NewsNERTagger, Doc
from rapidfuzz import fuzz

from gazetteers import COMPANY_NAMES, COMPANY_PRODUCTS, COMPETITORS

_segmenter: Segmenter = Segmenter()
_embedding: NewsEmbedding = NewsEmbedding()
_ner_tagger: NewsNERTagger = NewsNERTagger(_embedding)

FUZZY_THRESHOLD: int = 85
MIN_LENGTH_RATIO: float = 0.6  # candidate не может быть короче 60% длины term


@dataclass
class EntityMatchResult:
    company_mentioned: bool = False
    matched_company_terms: list[str] = field(default_factory=list)
    competitor_mentioned: bool = False
    matched_competitor_terms: list[str] = field(default_factory=list)
    extracted_orgs: list[str] = field(default_factory=list)


def extract_organizations(text: str) -> list[str]:
    doc: Doc = Doc(text)
    doc.segment(_segmenter)
    doc.tag_ner(_ner_tagger)

    return [span.text for span in doc.spans if span.type == "ORG"]


def _fuzzy_contains(candidate: str, terms: list[str], threshold: int = FUZZY_THRESHOLD) -> str | None:
    candidate_clean: str = candidate.strip().lower()
    if len(candidate_clean) < 3:
        return None

    for term in terms:
        term_clean: str = term.strip().lower()
        if len(candidate_clean) < MIN_LENGTH_RATIO * len(term_clean):
            continue

        score: float = fuzz.partial_ratio(candidate_clean, term_clean)
        if score >= threshold:
            return term

    return None


def _substring_matches(text: str, terms: list[str]) -> list[str]:
    text_lower: str = text.lower()
    return [term for term in terms if term.lower() in text_lower]


def match_entities(text: str) -> EntityMatchResult:
    result: EntityMatchResult = EntityMatchResult()

    orgs: list[str] = extract_organizations(text)
    result.extracted_orgs = orgs

    company_terms: list[str] = COMPANY_NAMES + COMPANY_PRODUCTS

    for org in orgs:
        matched_company: str | None = _fuzzy_contains(org, company_terms)
        if matched_company:
            result.company_mentioned = True
            result.matched_company_terms.append(matched_company)

        matched_competitor: str | None = _fuzzy_contains(org, COMPETITORS)
        if matched_competitor:
            result.competitor_mentioned = True
            result.matched_competitor_terms.append(matched_competitor)

    for term in _substring_matches(text, company_terms):
        if term not in result.matched_company_terms:
            result.company_mentioned = True
            result.matched_company_terms.append(term)

    for term in _substring_matches(text, COMPETITORS):
        if term not in result.matched_competitor_terms:
            result.competitor_mentioned = True
            result.matched_competitor_terms.append(term)

    return result


if __name__ == "__main__":
    samples: list[str] = [
        "«Триколор» совместно с технологическим партнером GS Labs завершил "
        "тестирование системы условного доступа CAS Dreguard.",
        "Российский разработчик IPTVPORTAL представил обновление платформы для операторов.",
        "Прогноз погоды на сентябрь 2026 года в Москве.",
    ]
    for s in samples:
        r: EntityMatchResult = match_entities(s)
        print(s)
        print("  ORGs:", r.extracted_orgs)
        print("  company:", r.company_mentioned, r.matched_company_terms)
        print("  competitor:", r.competitor_mentioned, r.matched_competitor_terms)
        print()
