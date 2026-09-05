from typing import List, Optional

from pydantic import BaseModel, Field

class SourceOut(BaseModel):
    id: str
    name: str
    group: str
    type: str
    url: str = ""
    status: str
    last_fetch: str
    category_default: str
    poll_interval: str
    count: int = 0

class SourceGroupOut(BaseModel):
    name: str
    sources: List[SourceOut]

class SourcesPayload(BaseModel):
    general_count: int
    groups: List[SourceGroupOut]

class GetSourcesResponse(BaseModel):
    sources: SourcesPayload

class AddSourceRequest(BaseModel):
    name: str
    url: Optional[str] = ""
    group: Optional[str] = None
    type: Optional[str] = None
    category: Optional[str] = "Экономика"
    poll_interval: Optional[str] = "Каждые 15 минут"

class AddSourceResponse(BaseModel):
    source: SourceOut

class ChangeSourceRequest(BaseModel):
    id: str
    name: Optional[str] = None
    url: Optional[str] = None
    status: Optional[str] = None
    category_default: Optional[str] = None
    poll_interval: Optional[str] = None
    action: Optional[str] = None

class ChangeSourceResponse(BaseModel):
    source: SourceOut

class RemoveSourceRequest(BaseModel):
    id: str

class NewsOut(BaseModel):
    id: str
    source: str
    source_name: str
    title: str
    link: str = ""
    author: str = "—"
    category: Optional[str] = None
    importance: Optional[str] = None
    description: str = ""
    pub_date: str = ""
    paragraphs: int = 1
    who: Optional[str] = None
    what: Optional[str] = None
    when: Optional[str] = None
    consequences: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    in_general: bool = True
    added_manually: bool = False
    added_by: Optional[str] = None
    mention_source: Optional[str] = None
    hidden: bool = False
    entity_id: Optional[str] = None
    object_type: Optional[str] = None
    plot_count: int = 1
    lifecycle: List[dict] = Field(default_factory=list)
    text: str = ""

class GetNewsResponse(BaseModel):
    source: str
    news: List[NewsOut]

class AddNewsRequest(BaseModel):
    title: str
    description: Optional[str] = ""
    category: Optional[str] = None
    importance: Optional[str] = None
    link: Optional[str] = ""
    pub_date: Optional[str] = None
    author: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list)
    in_general: Optional[bool] = True
    source: Optional[str] = None
    added_by: Optional[str] = None
    who: Optional[str] = None
    what: Optional[str] = None
    when: Optional[str] = None
    consequences: Optional[str] = None

class AddNewsResponse(BaseModel):
    news: NewsOut

class ChangeNewsRequest(BaseModel):
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    importance: Optional[str] = None
    link: Optional[str] = None
    tags: Optional[List[str]] = None
    in_general: Optional[bool] = None
    hidden: Optional[bool] = None
    who: Optional[str] = None
    what: Optional[str] = None
    when: Optional[str] = None
    consequences: Optional[str] = None

class ChangeNewsResponse(BaseModel):
    news: NewsOut

class RemoveNewsRequest(BaseModel):
    id: str

class OkResponse(BaseModel):
    ok: bool = True

class ErrorResponse(BaseModel):
    error: str
