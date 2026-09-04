import os
import re
from typing import Optional
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from .http import get_xml_text, session
from .models import NpaDocument, NpaEvent

SOZD_BILL = "https://sozd.duma.gov.ru/bill/{number}"
SOZD_RSS = "https://sozd.duma.gov.ru/bill/{number}/rss"
DUMA_SEARCH = "http://api.duma.gov.ru/api/{token}/search.json"
BILL_RE = re.compile(r"(\d{5,7}-\d)")


def bill_number_from_url(url: str) -> Optional[str]:
    path = urlparse(url).path
    m = re.search(r"/bill/(\d{5,7}-\d)", path)
    if m:
        return m.group(1)
    m = BILL_RE.search(url)
    return m.group(1) if m else None


def _parse_event_title(raw: str) -> tuple[Optional[str], str]:
    text = (raw or "").strip()
    m = re.match(r"\((\d{2}\.\d{2}\.\d{4}[^)]*)\)\s*(.*)", text)
    if m:
        return m.group(1), m.group(2).strip()
    return None, text


def _guess_event_type(title: str) -> str:
    t = (title or "").lower()
    if "регистрация законопроекта" in t or "1.1" in t:
        return "introduced"
    if "чтение" in t:
        return "reading"
    if "опублик" in t:
        return "published"
    if "отзыв" in t or "изменен" in t:
        return "revision"
    return "stage"


class SozdParser:
    def __init__(self, api_token: Optional[str] = None):
        self.session = session()
        self.api_token = api_token or os.environ.get("DUMA_API_TOKEN", "").strip()

    def get_bill(self, number: str) -> NpaDocument:
        number = number.strip()
        passport = self._parse_passport(number)
        events = self._parse_events_rss(number)
        if self.api_token:
            api = self._search_api(number)
            if api:
                passport.update(api)

        paragraphs = []
        if passport.get("title"):
            paragraphs.append(passport["title"])
        for k, v in passport.get("fields", {}).items():
            if v:
                paragraphs.append(f"{k}: {v}")
        for ev in events:
            if ev.summary:
                paragraphs.append(f"{ev.date or ''} {ev.title}: {ev.summary}".strip())

        stage = None
        if events:
            stage = events[0].title  # RSS идёт от нового к старому

        return NpaDocument(
            source="sozd.duma.gov.ru",
            official_id=number,
            id_type="sozd_bill",
            title=passport.get("title") or f"Законопроект № {number}",
            link=SOZD_BILL.format(number=number),
            stage=stage,
            kind=passport.get("fields", {}).get("Форма законопроекта"),
            department=passport.get("fields", {}).get("Ответственный комитет"),
            summary=passport.get("title"),
            text="\n\n".join(paragraphs),
            paragraphs=paragraphs,
            events=events,
            extra={"fields": passport.get("fields", {})},
        )

    def recent_bill_numbers(self, *, limit: int = 30) -> list[str]:
        resp = self.session.get("https://sozd.duma.gov.ru/", timeout=40)
        resp.raise_for_status()
        found = list(dict.fromkeys(BILL_RE.findall(resp.text or "")))
        return found[:limit]

    def fetch_url(self, url: str) -> Optional[NpaDocument]:
        number = bill_number_from_url(url)
        if not number:
            return None
        return self.get_bill(number)

    def _parse_passport(self, number: str) -> dict:
        resp = self.session.get(SOZD_BILL.format(number=number), timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        title = ""
        tagged = soup.find(attrs={"data-title": True})
        if tagged and tagged.get("data-title"):
            title = tagged["data-title"].strip()
            title = re.sub(r"^Законопроект\s*№\s*\d+-\d+\s*", "", title).strip()
        fields: dict[str, str] = {}
        for tr in soup.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            key = cells[0].get_text(" ", strip=True)
            val = cells[1].get_text(" ", strip=True)
            if key and val and len(key) < 80 and "bhi" not in val:
                fields[key] = val
        return {"title": title, "fields": fields}

    def _parse_events_rss(self, number: str) -> list[NpaEvent]:
        resp = self.session.get(SOZD_RSS.format(number=number), timeout=30)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        channel = root.find("channel")
        if channel is None:
            return []
        events: list[NpaEvent] = []
        for item in channel.findall("item"):
            raw_title = get_xml_text(item.find("title"))
            date, title = _parse_event_title(raw_title)
            summary = get_xml_text(item.find("description"))
            link = get_xml_text(item.find("link")) or SOZD_BILL.format(number=number)
            events.append(
                NpaEvent(
                    source="sozd.duma.gov.ru",
                    official_id=number,
                    id_type="sozd_bill",
                    event_type=_guess_event_type(title),
                    title=title,
                    link=link,
                    date=date,
                    summary=summary,
                    stage=title,
                )
            )
        return events

    def _search_api(self, number: str) -> dict:
        url = DUMA_SEARCH.format(token=self.api_token)
        resp = self.session.get(url, params={"number": number}, timeout=30)
        if resp.status_code >= 400:
            return {}
        try:
            data = resp.json()
        except ValueError:
            return {}
        laws = data if isinstance(data, list) else data.get("laws") or data.get("result") or []
        if not laws:
            return {}
        first = laws[0] if isinstance(laws, list) else laws
        if not isinstance(first, dict):
            return {}
        return {
            "title": first.get("name") or first.get("comments") or "",
            "api": first,
        }
