import re
from typing import Optional
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from .http import get_xml_text, session
from .models import NpaDocument, NpaEvent

API_URL = "https://regulation.gov.ru/api/npalist"
PROJECT_URL = "https://regulation.gov.ru/projects/{id}/"


def project_id_from_url(url: str) -> Optional[str]:
    path = urlparse(url).path.strip("/")
    m = re.search(r"projects/(\d+)", path)
    return m.group(1) if m else None


def _el_attr_text(el) -> tuple[Optional[str], str]:
    if el is None:
        return None, ""
    return el.attrib.get("id"), get_xml_text(el)


def _parse_project(el) -> NpaDocument:
    pid = el.attrib.get("id") or ""
    title = get_xml_text(el.find("title"))
    stage_id, stage = _el_attr_text(el.find("stage"))
    status_id, status = _el_attr_text(el.find("status"))
    kind_id, kind = _el_attr_text(el.find("kind"))
    dep_id, department = _el_attr_text(el.find("department"))
    problem = get_xml_text(el.find("problem"))
    rationale = get_xml_text(el.find("rationale"))
    social = get_xml_text(el.find("socialRelations"))
    summary_parts = [p for p in (problem, rationale, social) if p]
    paragraphs = summary_parts
    start = get_xml_text(el.find("startDiscussion"))
    end = get_xml_text(el.find("endDiscussion"))

    extra = {
        "project_id": get_xml_text(el.find("projectId")),
        "date": get_xml_text(el.find("date")),
        "publish_date": get_xml_text(el.find("publishDate")),
        "procedure": get_xml_text(el.find("procedure")),
        "responsible": get_xml_text(el.find("responsible")),
        "start_discussion": start,
        "end_discussion": end,
        "plan_date": get_xml_text(el.find("planDate")),
        "regulatory_impact": get_xml_text(el.find("regulatoryImpact")),
        "stage_id": stage_id,
        "status_id": status_id,
        "kind_id": kind_id,
        "department_id": dep_id,
    }

    events: list[NpaEvent] = []
    if extra["publish_date"]:
        events.append(
            NpaEvent(
                source="regulation.gov.ru",
                official_id=pid,
                id_type="regulation_project",
                event_type="draft",
                title=f"Проект размещён: {title}",
                link=PROJECT_URL.format(id=pid),
                date=extra["publish_date"],
                summary=problem or title,
                stage=stage,
                status=status,
                kind=kind,
                department=department,
            )
        )
    if start or end:
        events.append(
            NpaEvent(
                source="regulation.gov.ru",
                official_id=pid,
                id_type="regulation_project",
                event_type="discussion",
                title=f"Публичное обсуждение: {title}",
                link=PROJECT_URL.format(id=pid),
                date=end or start,
                summary=f"Обсуждение {start or '—'} — {end or '—'}",
                stage=stage,
                status=status,
                kind=kind,
                department=department,
            )
        )

    return NpaDocument(
        source="regulation.gov.ru",
        official_id=pid,
        id_type="regulation_project",
        title=title,
        link=PROJECT_URL.format(id=pid),
        stage=stage,
        status=status,
        kind=kind,
        department=department,
        summary=problem or rationale or title,
        text="\n\n".join(paragraphs),
        paragraphs=paragraphs,
        events=events,
        extra=extra,
    )


class RegulationParser:
    def __init__(self):
        self.session = session()

    def get_project(self, project_id: str) -> Optional[NpaDocument]:
        resp = self.session.get(API_URL, params={"id": str(project_id)}, timeout=30)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        el = root.find("project")
        if el is None:
            return None
        return _parse_project(el)

    def list_recent(self, *, limit: int = 100, offset: int = 0) -> list[NpaDocument]:
        resp = self.session.get(
            API_URL,
            params={"limit": int(limit), "offset": int(offset), "sort": "desc"},
            timeout=90,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        return [_parse_project(el) for el in root.findall("project")]

    def search(self, query: str, *, limit: int = 20) -> list[NpaDocument]:
        resp = self.session.get(
            API_URL,
            params={"search": query, "limit": limit, "sort": "desc"},
            timeout=30,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        return [_parse_project(el) for el in root.findall("project")]

    def fetch_url(self, url: str) -> Optional[NpaDocument]:
        pid = project_id_from_url(url)
        if not pid:
            return None
        return self.get_project(pid)
