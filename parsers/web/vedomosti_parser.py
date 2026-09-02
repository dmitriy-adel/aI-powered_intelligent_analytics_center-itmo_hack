
from __future__ import annotations
 
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Optional
from xml.etree import ElementTree as ET
 
import requests
from bs4 import BeautifulSoup
 
RSS_URL = "https://www.vedomosti.ru/rss/news.xml"
 
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}
 
 
@dataclass
class NewsItem:
    title: str
    link: str
    guid: Optional[str] = None
    author: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    pub_date: Optional[str] = None
    text: Optional[str] = None
    paragraphs: list[str] = field(default_factory=list)
 
    def to_dict(self) -> dict:
        return asdict(self)
 
 
def parse_rss(url: str = RSS_URL, session: Optional[requests.Session] = None) -> list[NewsItem]:
    """Download the RSS feed and return a list of NewsItem (without article text)."""
    session = session or requests.Session()
    resp = session.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
 
    root = ET.fromstring(resp.content)
    channel = root.find("channel")
    if channel is None:
        raise ValueError("<channel> tag not found in the RSS feed")
 
    items: list[NewsItem] = []
    for item_el in channel.findall("item"):
        def text_of(tag: str) -> Optional[str]:
            el = item_el.find(tag)
            return el.text.strip() if el is not None and el.text else None
 
        enclosure_el = item_el.find("enclosure")
        image = enclosure_el.get("url") if enclosure_el is not None else None
 
        items.append(
            NewsItem(
                title=text_of("title") or "",
                link=text_of("link") or "",
                guid=text_of("guid"),
                author=text_of("author"),
                category=text_of("category"),
                description=text_of("description"),
                image=image,
                pub_date=text_of("pubDate"),
            )
        )
    return items
 
 
def _clean_paragraph_text(p_tag) -> str:
    """
    Carefully extract paragraph text that is "broken up" by <a> links.
    """
    raw = p_tag.get_text(separator=" ", strip=True)
    # collapse repeated whitespace / line breaks
    text = re.sub(r"\s+", " ", raw)
    # remove space before punctuation and closing guillemets
    text = re.sub(r"\s+([,.!?;:»])", r"\1", text)
    # remove space right after an opening guillemet «
    text = re.sub(r"(«)\s+", r"\1", text)

    return text.strip()
 
 
def parse_article(url: str, session: Optional[requests.Session] = None) -> dict:
    """
    Download an article page and extract its body text.
 
    On vedomosti.ru the text lives inside:
        div.article-boxes-list.article__boxes
          div.article-boxes-list__item
            div.box-paragraph
              p.box-paragraph__text   <-- the actual paragraph (may contain <a>)
 
    Returns {"text": "joined text", "paragraphs": [list of paragraphs]}.
    """
    session = session or requests.Session()
    resp = session.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
 
    soup = BeautifulSoup(resp.text, "lxml")
 
    boxes = soup.select_one("div.article-boxes-list")
    paragraphs: list[str] = []
 
    if boxes:
        for p in boxes.select("p.box-paragraph__text"):
            para = _clean_paragraph_text(p)
            if para:
                paragraphs.append(para)
    else:
        for p in soup.select("div.article__body p"):
            para = _clean_paragraph_text(p)

            if para:
                paragraphs.append(para)
 
    return {
        "text": "\n\n".join(paragraphs),
        "paragraphs": paragraphs,
    }
 
 
def get_news(limit: Optional[int] = None, delay: float = 0.5, rss_url: str = RSS_URL) -> list[dict]:

    session = requests.Session()
    items = parse_rss(rss_url, session=session)
    if limit is not None:
        items = items[:limit]
 
    result = []
    for item in items:
        try:
            article = parse_article(item.link, session=session)
            item.text = article["text"]
            item.paragraphs = article["paragraphs"]

        except Exception as exc:  
            item.text = None
            item.paragraphs = []
            print(f"[WARN] Failed to parse {item.link}: {exc}")
        
        result.append(item.to_dict())
        time.sleep(delay)
 
    return result
 
 
def _print_news_item(n: dict, preview_len: int = 300) -> None:
    """Pretty-print a single news dict for the __main__ test run."""
    text = n.get("text") or ""
    preview = text[:preview_len].strip()
    if len(text) > preview_len:
        preview += " […]"
 
    fields = [
        ("Title", n.get("title")),
        ("Link", n.get("link")),
        ("Author", n.get("author") or "—"),
        ("Category", n.get("category") or "—"),
        ("Description", n.get("description") or "—"),
        ("Image", n.get("image") or "—"),
        ("Published", n.get("pub_date") or "—"),
        ("Paragraphs", len(n.get("paragraphs") or [])),
    ]
 
    print("-" * 80)
    label_width = max(len(label) for label, _ in fields)
    for label, value in fields:
        print(f"{label:<{label_width}} : {value}")

    print()
    print("Text preview:")
    print(preview if preview else "(no text extracted)")
 
 
if __name__ == "__main__":
    news = get_news(limit=3)
    print(f"Fetched {len(news)} news item(s)\n")
    for n in news:
        _print_news_item(n)

    print("-" * 80)
