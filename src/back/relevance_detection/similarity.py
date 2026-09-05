from __future__ import annotations

import re

import pymorphy3
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from gazetteers import BUSINESS_DOMAINS, BusinessDomain

_morph: pymorphy3.MorphAnalyzer = pymorphy3.MorphAnalyzer()
_token_re: re.Pattern[str] = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)
_po_abbrev_re: re.Pattern[str] = re.compile(r"\bПО\b")

RUSSIAN_STOPWORDS: list[str] = [
    "по", "на", "из", "от", "до", "при", "для", "же", "бы", "ли", "что",
    "как", "это", "то", "не", "ни", "за", "под", "над", "об", "во", "со",
    "из-за", "если", "но", "или", "и", "а", "все", "всех", "его", "ее",
    "их", "он", "она", "они", "мы", "вы", "быть", "который", "также",
    "уже", "еще", "может", "будет", "года", "год", "время", "лишь",
]


def lemmatize(text: str) -> str:
    text = _po_abbrev_re.sub("программноеобеспечение", text)
    tokens: list[str] = _token_re.findall(text.lower())
    lemmas: list[str] = [_morph.parse(t)[0].normal_form for t in tokens]

    return " ".join(w for w in lemmas if w not in RUSSIAN_STOPWORDS)


class SimilarityScorer:
    def score(self, text: str) -> dict[str, float]:
        raise NotImplementedError


class TfidfSimilarityScorer(SimilarityScorer):

    def __init__(self, domains: list[BusinessDomain] = BUSINESS_DOMAINS) -> None:
        self.domains: list[BusinessDomain] = domains
        self.domain_texts: list[str] = [
            lemmatize(d.description + " " + " ".join(d.keywords)) for d in domains
        ]

    def score(self, text: str) -> dict[str, float]:
        corpus: list[str] = self.domain_texts + [lemmatize(text)]
        vectorizer: TfidfVectorizer = TfidfVectorizer(ngram_range=(2, 2))
        try:
            tfidf = vectorizer.fit_transform(corpus)
            
        except ValueError:
            return {d.name: 0.0 for d in self.domains}

        text_vector = tfidf[-1]
        domain_vectors = tfidf[:-1]
        sims = cosine_similarity(text_vector, domain_vectors)[0]
        return {d.name: float(s) for d, s in zip(self.domains, sims)}


if __name__ == "__main__":
    scorer: TfidfSimilarityScorer = TfidfSimilarityScorer()
    samples: list[str] = [
        "Правительство включило системы условного доступа в перечень объектов КИИ.",
        "Новые правила ведения реестра российского ПО вступают в силу с 1 марта 2026 года.",
        "Прогноз погоды на сентябрь 2026 года в Москве.",
    ]
    for s in samples:
        print(s)
        for domain, sim in scorer.score(s).items():
            print(f"  {domain}: {sim:.3f}")
            
        print()
