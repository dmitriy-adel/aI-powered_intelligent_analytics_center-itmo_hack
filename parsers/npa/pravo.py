import re
from typing import Optional
from urllib.parse import urlparse

from .http import session
from .models import NpaDocument, NpaEvent

BASE = "http://publication.pravo.gov.ru"
DOC_PAGE = "http://publication.pravo.gov.ru/document/{eo}"
EO_RE = re.compile(r"(0001\d{12}|\d{16})")


def eo_from_url(url: str) -> Optional[str]:
    path = urlparse(url).path
    m = re.search(r"/document/([0-9A-Za-z]+)", path)
    if m:
        return m.group(1)
    m = EO_RE.search(url)
    return m.group(1) if m else None


def _item_to_doc(item: dict) -> NpaDocument:
    eo = item.get("eoNumber") or ""
    title = item.get("name") or item.get("complexName") or item.get("title") or ""
    title = re.sub(r"<br\s*/?>", " ", title, flags=re.I)
    authorities = item.get("signatoryAuthorities") or []
    department = None
    if authorities:
        department = authorities[0].get("name")
    elif item.get("signatoryAuthority"):
        department = str(item.get("signatoryAuthority"))
    doc_type = (item.get("documentType") or {}).get("name") if isinstance(item.get("documentType"), dict) else None
    date = item.get("publishDateShort") or item.get("viewDate") or item.get("documentDate")
    number = item.get("number")
    summary = item.get("complexName") or title
    paragraphs = [p for p in (title, summary) if p]
    extra = {
        "number": number,
        "document_date": item.get("documentDate"),
        "publish_date": item.get("publishDateShort"),
        "pages": item.get("pagesCount"),
        "pdf_bytes": item.get("pdfFileLength"),
        "raw": {k: item[k] for k in item if k not in {"signatoryAuthorities"}},
    }
    event = NpaEvent(
        source="publication.pravo.gov.ru",
        official_id=eo,
        id_type="pravo_eo",
        event_type="published",
        title=f"Официально опубликован акт № {number or eo}",
        link=DOC_PAGE.format(eo=eo),
        date=date,
        summary=title,
        stage="Опубликован",
        kind=doc_type,
        department=department,
    )
    return NpaDocument(
        source="publication.pravo.gov.ru",
        official_id=eo,
        id_type="pravo_eo",
        title=title,
        link=DOC_PAGE.format(eo=eo),
        stage="Опубликован",
        kind=doc_type,
        department=department,
        summary=summary,
        text="\n\n".join(paragraphs),
        paragraphs=paragraphs,
        events=[event],
        extra=extra,
    )


class PravoParser:
    def __init__(self):
        self.session = session()

    def get_document(self, eo_number: str) -> Optional[NpaDocument]:
        resp = self.session.get(
            f"{BASE}/api/Document",
            params={"eoNumber": eo_number},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data or not data.get("eoNumber"):
            return None
        return _item_to_doc(data)

    def search(
        self,
        *,
        name: Optional[str] = None,
        number: Optional[str] = None,
        publish_from: Optional[str] = None,
        publish_to: Optional[str] = None,
        page: int = 1,
    ) -> list[NpaDocument]:
        params: dict = {"CurrentPage": page}
        if name:
            params["Name"] = name
        if number:
            params["Number"] = number
        if publish_from:
            params["PublishDateFrom"] = publish_from
        if publish_to:
            params["PublishDateTo"] = publish_to
        resp = self.session.get(f"{BASE}/api/Documents", params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json() or {}
        return [_item_to_doc(it) for it in payload.get("items") or []]

    def fetch_url(self, url: str) -> Optional[NpaDocument]:
        eo = eo_from_url(url)
        if not eo:
            return None
        return self.get_document(eo)
