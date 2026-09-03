
from __future__ import annotations
 
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
 
import requests
from bs4 import BeautifulSoup
 
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}
 
DEFAULT_DELAY = 10
 
 
# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
 
@dataclass
class NewsItem:
    """Unified news record — same shape regardless of which source it came from.
    """
 
    source: str
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
 
 
# --------------------------------------------------------------------------- #
# Per-source configuration — the only place that should grow when a new
# source is added.
# --------------------------------------------------------------------------- #
 
@dataclass
class SourceConfig:
    name: str
    domain: str  
    rss_url: str
    wrapper_selector: str
    paragraph_selector: Optional[str]
    fallback_selector: str
    dedupe: bool = False
 
 
SOURCES: list[SourceConfig] = [
    SourceConfig(
        name="Vedomosti",
        domain="vedomosti.ru",
        rss_url="https://www.vedomosti.ru/rss/news.xml",
        wrapper_selector="div.article-boxes-list",
        paragraph_selector="p.box-paragraph__text",
        fallback_selector="div.article__body p",
    ),
    SourceConfig(
        name="Kommersant",
        domain="kommersant.ru",
        rss_url="https://www.kommersant.ru/rss/news.xml",
        wrapper_selector='div[id^="article-text-"], div.article_text_wrapper',
        paragraph_selector="p.doc__text",
        fallback_selector="div.doc_body p.doc__text",
    ),
    SourceConfig(
        name="Telesputnik",
        domain="telesputnik.ru",
        rss_url="https://telesputnik.ru/rss/",
        wrapper_selector="div.page-article__wrapper",
        paragraph_selector=None,
        fallback_selector="main.page-article p",
        dedupe=True,
    ),
]
 
 
def _resolve_source(url: str) -> SourceConfig:
    """Pick the SourceConfig matching the given URL's domain."""
    host = urlparse(url).netloc.lower()
    for source in SOURCES:
        if source.domain in host:
            return source
        
    known = ", ".join(s.domain for s in SOURCES)
    raise ValueError(f"No source configuration found for URL '{url}'. Known sources: {known}")
 
 
# --------------------------------------------------------------------------- #
# Shared parsing logic
# --------------------------------------------------------------------------- #
 
def _clean_paragraph_text(p_tag) -> str:
    """
    Carefully extract paragraph text that is "broken up" by <a> links.
    """
    raw = p_tag.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", raw)  # collapse repeated whitespace / line breaks
    text = re.sub(r"\s+([,.!?;:»])", r"\1", text)  # no space before punctuation/»
    text = re.sub(r"(«)\s+", r"\1", text)  # no space right after «
    return text.strip()
 
 
def _parse_pub_date(pub_date: Optional[str]) -> Optional[datetime]:
    """Parse an RFC 2822 pubDate string (as used by RSS) into a datetime."""
    if not pub_date:
        return None
    
    try:
        return parsedate_to_datetime(pub_date)
    
    except (TypeError, ValueError):
        return None
 
 
class WebParsers:
    """Fetches and parses news from Vedomosti, Kommersant and Telesputnik."""
 
    def __init__(self, headers: Optional[dict] = None):
        self.headers = headers or HEADERS
        self.session = requests.Session()
 
    # -- RSS ----------------------------------------------------------------
 
    def _parse_rss(self, source: SourceConfig, rss_url: str) -> list[NewsItem]:
        """Download the RSS feed and return a list of NewsItem (no article text yet)."""
        resp = self.session.get(rss_url, headers=self.headers, timeout=15)
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
                    source=source.name,
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
 
    # -- Article body ---------------------------------------------------------
 
    def _parse_article(self, source: SourceConfig, url: str) -> dict:
        """Download an article page and extract its body text using the
        source's configured selectors."""
        resp = self.session.get(url, headers=self.headers, timeout=15)
        resp.raise_for_status()
 
        soup = BeautifulSoup(resp.text, "lxml")
 
        wrapper = soup.select_one(source.wrapper_selector)
        paragraphs: list[str] = []
        seen: set[str] = set()
 
        def collect(p_tags) -> None:
            for p in p_tags:
                para = _clean_paragraph_text(p)
                if not para:
                    continue
                if source.dedupe:
                    if para in seen:
                        continue
                    seen.add(para)
                paragraphs.append(para)
 
        if wrapper:
            p_tags = wrapper.select(source.paragraph_selector) if source.paragraph_selector else wrapper.find_all("p")
            collect(p_tags)

        else:
            collect(soup.select(source.fallback_selector))
 
        return {
            "text": "\n\n".join(paragraphs),
            "paragraphs": paragraphs,
        }
 
    # -- Public API -----------------------------------------------------------
 
    def parse_page(self, url: str, limit: Optional[int] = None, 
                   until: Optional[datetime] = None, delay: float = DEFAULT_DELAY) -> list[dict]:
        """
        Full pipeline for one source: RSS -> filtered items -> article text
        fetched for each one.
        """
        source = _resolve_source(url)
        items = self._parse_rss(source, url)
 
        if until is not None:
            filtered: list[NewsItem] = []
            for item in items:
                pub_dt = _parse_pub_date(item.pub_date)
                if pub_dt is None:
                    filtered.append(item)
                    continue

                cmp_dt = pub_dt if until.tzinfo else pub_dt.replace(tzinfo=None)
                if cmp_dt >= until:
                    filtered.append(item)

                else:
                    break

            items = filtered
 
        if limit is not None:
            items = items[:limit]
 
        result = []
        for item in items:
            try:
                article = self._parse_article(source, item.link)
                item.text = article["text"]
                item.paragraphs = article["paragraphs"]
            
            except Exception as exc:  
                item.text = None
                item.paragraphs = []
                print(f"[WARN] Failed to parse {item.link}: {exc}")

            result.append(item.to_dict())
            time.sleep(delay)
 
        return result
 
    def parse_many(self, requests_spec: list[dict], max_workers: Optional[int] = None) -> dict[str, list[dict]]:
        """
        Parse several sources concurrently instead of one after another.
        """
 
        def worker(spec: dict) -> tuple[str, list[dict]]:
            source_name = _resolve_source(spec["url"]).name
            local_parser = WebParsers(headers=self.headers)
            data = local_parser.parse_page(
                url=spec["url"],
                limit=spec.get("limit"),
                until=spec.get("until"),
                delay=spec.get("delay", DEFAULT_DELAY),
            )
            return source_name, data
 
        results: dict[str, list[dict]] = {}
        with ThreadPoolExecutor(max_workers=max_workers or len(requests_spec)) as executor:
            futures = [executor.submit(worker, spec) for spec in requests_spec]
            for future in as_completed(futures):
                source_name, data = future.result()
                results[source_name] = data
 
        return results
 
 
# --------------------------------------------------------------------------- #
# Demo / test run
# --------------------------------------------------------------------------- #
 
def _print_news_item(n: dict, preview_len: int = 300) -> None:
    """Pretty-print a single news dict for the __main__ test run."""
    text = n.get("text") or ""
    preview = text[:preview_len].strip()
    if len(text) > preview_len:
        preview += " […]"
 
    fields = [
        ("Source", n.get("source")),
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
    parser = WebParsers()
 
    requests_spec = [
        {"url": "https://www.vedomosti.ru/rss/news.xml", "limit": 2, "delay": 5},
        {"url": "https://www.kommersant.ru/rss/news.xml", "limit": 2, "delay": 5},
        {"url": "https://telesputnik.ru/rss/", "limit": 2, "delay": 5},
    ]
 
    start = time.monotonic()
    results = parser.parse_many(requests_spec)
    elapsed = time.monotonic() - start
 
    for source_name, news in results.items():
        print(f"\n=== {source_name} — fetched {len(news)} news item(s) ===\n")
        for n in news:
            _print_news_item(n)
 
    print("-" * 80)
    print(f"Total wall-clock time for all sources: {elapsed:.1f}s")
