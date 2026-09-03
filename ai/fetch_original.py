import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "parsers" / "web"))

from web_parsers import HEADERS, WebParsers, _resolve_source

GENERIC_SELECTORS = [
    "article p",
    "main p",
    "div.article p",
    "div.content p",
    "div.post-content p",
    "div.entry-content p",
    "div.text p",
]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _generic_parse(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    title = ""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = _clean(og["content"])
    if not title:
        h1 = soup.find("h1")
        title = _clean(h1.get_text()) if h1 else ""

    paragraphs = []
    seen = set()
    for sel in GENERIC_SELECTORS:
        for p in soup.select(sel):
            para = _clean(p.get_text())
            if len(para) < 40 or para in seen:
                continue
            seen.add(para)
            paragraphs.append(para)
        if len(paragraphs) >= 3:
            break

    return {
        "title": title,
        "text": "\n\n".join(paragraphs),
        "paragraphs": paragraphs,
        "_fetch_method": "generic",
        "_source_url": url,
    }


def fetch_original_url(url: str) -> dict:
    url = (url or "").strip()
    if not url or url.startswith("GR-") or " " in url:
        return {
            "link": url,
            "text": "",
            "paragraphs": [],
            "_fetch_error": "invalid_or_non_http_url",
            "_fetch_method": "skipped",
        }

    for part in re.split(r"[\s,]+", url):
        if part.startswith("http"):
            url = part
            break

    sess = requests.Session()
    host = urlparse(url).netloc.lower()
    generic_error = None

    try:
        source = _resolve_source(url)
        parser = WebParsers()
        parser.session = sess
        body = parser._parse_article(source, url)
        return {
            "link": url,
            "source": source.name,
            "title": "",
            "text": body.get("text") or "",
            "paragraphs": body.get("paragraphs") or [],
            "_fetch_method": "web_parsers",
        }
    except ValueError:
        pass
    except Exception as exc:
        generic_error = str(exc)

    try:
        resp = sess.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
        resp.raise_for_status()
        parsed = _generic_parse(resp.text, url)
        parsed["link"] = url
        parsed["source"] = host
        return parsed
    except Exception as exc:
        return {
            "link": url,
            "text": "",
            "paragraphs": [],
            "_fetch_error": generic_error or str(exc),
            "_fetch_method": "failed",
        }


def merge_excel_with_original(excel_card: dict, fetched: dict) -> dict:
    merged = dict(excel_card)
    merged["link"] = fetched.get("link") or excel_card.get("link")
    merged["title_original_excel"] = excel_card.get("title")
    merged["excel_summary"] = excel_card.get("description") or ""

    if fetched.get("title"):
        merged["title"] = fetched["title"]
    if fetched.get("source"):
        merged["source"] = fetched["source"]

    text = (fetched.get("text") or "").strip()
    if text:
        merged["text"] = text
        merged["paragraphs"] = fetched.get("paragraphs") or []
        merged["_text_source"] = "original_url"
    else:
        merged["_text_source"] = "excel_fallback"
        merged["_fetch_error"] = fetched.get("_fetch_error")

    merged["_fetch_method"] = fetched.get("_fetch_method")
    return merged


def fetch_excel_originals(cards: list[dict], *, concurrency: int = 5) -> list[dict]:
    results = [None] * len(cards)

    def worker(idx, card):
        url = card.get("link") or ""
        try:
            fetched = fetch_original_url(url)
            merged = merge_excel_with_original(card, fetched)
        except Exception as exc:
            merged = merge_excel_with_original(
                card,
                {"link": url, "text": "", "paragraphs": [], "_fetch_error": str(exc), "_fetch_method": "failed"},
            )
        return idx, merged

    with ThreadPoolExecutor(max_workers=min(concurrency, len(cards) or 1)) as pool:
        futures = [pool.submit(worker, i, c) for i, c in enumerate(cards)]
        for fut in as_completed(futures):
            idx, merged = fut.result()
            results[idx] = merged
            ok = "OK" if (merged.get("text") or "").strip() else "EMPTY"
            print(f"  [{idx + 1}/{len(cards)}] {ok} {merged.get('link', '')[:70]}")

    return [r for r in results if r is not None]
