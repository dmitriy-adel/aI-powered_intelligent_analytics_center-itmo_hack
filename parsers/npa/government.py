import re
from typing import Optional
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from .http import get_xml_text, session
from .models import NpaDocument, NpaEvent

RSS_ALL = "http://government.ru/all/rss/"
NEWS_URL = "http://government.ru/news/{nid}/"
ID_RE = re.compile(r"/news/(\d+)")
BILL_RE = re.compile(r"\b(\d{6,7}-\d)\b")
PP_RE = re.compile(r"(?:ПП|постановлен\w+\s+Правительства)[^\d]{0,12}№\s*(\d+)", re.I)
FZ_RE = re.compile(r"(?:ФЗ|федеральн\w+\s+закон)[^\d]{0,12}№\s*([\d-]+)", re.I)


def news_id_from_url(url: str) -> Optional[str]:
    m = ID_RE.search(urlparse(url).path)
    return m.group(1) if m else None


def _extract_related_ids(text: str) -> dict:
    found = {
        "sozd_bills": sorted(set(BILL_RE.findall(text or ""))),
        "pp_numbers": sorted(set(PP_RE.findall(text or ""))),
        "fz_numbers": sorted(set(FZ_RE.findall(text or ""))),
    }
    return {k: v for k, v in found.items() if v}


class GovernmentParser:
    def __init__(self):
        self.session = session()

    def fetch_rss(self, *, limit: int = 20, rss_url: str = RSS_ALL) -> list[NpaDocument]:
        resp = self.session.get(rss_url, timeout=30)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        channel = root.find("channel")
        if channel is None:
            return []
        docs: list[NpaDocument] = []
        for item in channel.findall("item")[:limit]:
            link = get_xml_text(item.find("link"))
            nid = news_id_from_url(link) or get_xml_text(item.find("guid"))
            title = get_xml_text(item.find("title"))
            date = get_xml_text(item.find("pubDate"))
            docs.append(
                NpaDocument(
                    source="government.ru",
                    official_id=str(nid or link),
                    id_type="government_news",
                    title=title,
                    link=link,
                    kind="Анонс",
                    summary=title,
                    events=[
                        NpaEvent(
                            source="government.ru",
                            official_id=str(nid or link),
                            id_type="government_news",
                            event_type="announcement",
                            title=title,
                            link=link,
                            date=date,
                            summary=title,
                            kind="Анонс",
                        )
                    ],
                    extra={"pub_date": date},
                )
            )
        return docs

    def fetch_article(self, url: str) -> Optional[NpaDocument]:
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        headline = soup.select_one(".reader_article_headline")
        title = headline.get_text(" ", strip=True) if headline else ""
        if not title and soup.title:
            title = soup.title.get_text(" ", strip=True)
        date_el = soup.select_one(".reader_article_dateline__date")
        date = date_el.get_text(" ", strip=True) if date_el else None
        lead_el = soup.select_one(".reader_article_lead")
        lead = lead_el.get_text(" ", strip=True) if lead_el else ""
        paragraphs: list[str] = []
        body = soup.select_one(".reader_article_body")
        if body:
            for p in body.find_all("p"):
                text = re.sub(r"\s+", " ", p.get_text(" ", strip=True)).strip()
                if len(text) >= 40:
                    paragraphs.append(text)
        if lead and lead not in paragraphs:
            paragraphs.insert(0, lead)
        nid = news_id_from_url(url) or ""
        full_text = "\n\n".join(paragraphs)
        related = _extract_related_ids(title + "\n" + full_text)
        return NpaDocument(
            source="government.ru",
            official_id=nid,
            id_type="government_news",
            title=title,
            link=url,
            kind="Анонс",
            summary=lead or (paragraphs[0] if paragraphs else title),
            text=full_text,
            paragraphs=paragraphs,
            events=[
                NpaEvent(
                    source="government.ru",
                    official_id=nid,
                    id_type="government_news",
                    event_type="announcement",
                    title=title,
                    link=url,
                    date=date,
                    summary=lead or title,
                    kind="Анонс",
                    extra=related,
                )
            ],
            extra={"pub_date": date, "related_ids": related},
        )

    def fetch_url(self, url: str) -> Optional[NpaDocument]:
        if "/rss" in urlparse(url).path:
            items = self.fetch_rss()
            return items[0] if items else None
        return self.fetch_article(url)
