from dataclasses import asdict, dataclass, field
from typing import Any, Optional

@dataclass
class NpaEvent:
    source: str
    official_id: str
    id_type: str  # sozd_bill | regulation_project | pravo_eo | government_news
    event_type: str  # draft | discussion | stage | published | announcement
    title: str
    link: str
    date: Optional[str] = None
    summary: Optional[str] = None
    stage: Optional[str] = None
    status: Optional[str] = None
    kind: Optional[str] = None
    department: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class NpaDocument:
    source: str
    official_id: str
    id_type: str
    title: str
    link: str
    stage: Optional[str] = None
    status: Optional[str] = None
    kind: Optional[str] = None
    department: Optional[str] = None
    summary: Optional[str] = None
    text: Optional[str] = None
    paragraphs: list[str] = field(default_factory=list)
    events: list[NpaEvent] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_article(self) -> dict:
        paragraphs = list(self.paragraphs)
        if not paragraphs and self.summary:
            paragraphs = [self.summary]
        return {
            "source": self.source,
            "title": self.title,
            "link": self.link,
            "guid": self.official_id,
            "author": self.department or "—",
            "category": "Регулирование",
            "description": self.summary,
            "pub_date": self.stage or self.status,
            "text": self.text or "\n\n".join(paragraphs),
            "paragraphs": paragraphs,
            "official_id": self.official_id,
            "id_type": self.id_type,
            "document_type_hint": "regulation" if self.id_type != "government_news" else "announcement",
            "npa_events": [e.to_dict() for e in self.events],
            "_fetch_method": f"npa_{self.id_type}",
        }
