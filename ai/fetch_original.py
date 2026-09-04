import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "parsers" / "web"))

from web_parsers import HEADERS, WebParsers, _resolve_source  # noqa: E402
from parsers.npa import fetch_npa_url  # noqa: E402

NPA_HOST_HINTS = (
    "regulation.gov.ru",
    "sozd.duma.gov.ru",
    "publication.pravo.gov.ru",
    "government.ru",
)

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

    paragraphs: list[str] = []
    seen: set[str] = set()
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


def fetch_original_url(url: str, *, session: Optional[requests.Session] = None) -> dict:
    """Скачивает оригинал статьи/документа по URL."""
    url = (url or "").strip()
    if not url or url.startswith("GR-"):
        return {
            "link": url,
            "text": "",
            "paragraphs": [],
            "_fetch_error": "invalid_or_non_http_url",
            "_fetch_method": "skipped",
        }

    http_parts = [p for p in re.split(r"[\s,]+", url) if p.startswith("http")]
    if http_parts:
        official = [p for p in http_parts if any(h in p.lower() for h in NPA_HOST_HINTS)]
        url = official[0] if official else http_parts[0]
    elif " " in url:
        return {
            "link": url,
            "text": "",
            "paragraphs": [],
            "_fetch_error": "invalid_or_non_http_url",
            "_fetch_method": "skipped",
        }

    sess = session or requests.Session()
    host = urlparse(url).netloc.lower()
    npa_error = None

    if any(h in host for h in NPA_HOST_HINTS):
        try:
            doc = fetch_npa_url(url)
            if doc:
                article = doc.to_article()
                if (article.get("text") or "").strip():
                    return article
        except Exception as exc:  # noqa: BLE001
            npa_error = str(exc)

    generic_error = npa_error
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
    except Exception as exc:  # noqa: BLE001
        generic_error = str(exc)

    try:
        resp = sess.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
        resp.raise_for_status()
        parsed = _generic_parse(resp.text, url)
        parsed["link"] = url
        parsed["source"] = host
        return parsed
    except Exception as exc:  # noqa: BLE001
        return {
            "link": url,
            "text": "",
            "paragraphs": [],
            "_fetch_error": generic_error or str(exc),
            "_fetch_method": "failed",
        }


def merge_excel_with_original(excel_card: dict, fetched: dict) -> dict:
    """Excel-метаданные + оригинальный текст (не саммари из таблицы)."""
    merged = dict(excel_card)
    merged["link"] = fetched.get("link") or excel_card.get("link")
    merged["title_original_excel"] = excel_card.get("title")
    merged["excel_summary"] = excel_card.get("description") or ""

    if fetched.get("title"):
        merged["title"] = fetched["title"]
    if fetched.get("source"):
        merged["source"] = fetched["source"]

    if fetched.get("official_id"):
        merged["official_id"] = fetched["official_id"]
        merged["id_type"] = fetched.get("id_type")
    if fetched.get("npa_events"):
        merged["npa_events"] = fetched["npa_events"]

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


def fetch_excel_originals(
    cards: list[dict],
    *,
    concurrency: int = 5,
) -> list[dict]:
    """Параллельно подтягивает оригиналы для списка Excel-карточек."""
    results: list[Optional[dict]] = [None] * len(cards)

    def worker(idx: int, card: dict) -> tuple[int, dict]:
        url = card.get("link") or ""
        try:
            fetched = fetch_original_url(url)
            merged = merge_excel_with_original(card, fetched)
        except Exception as exc:  # noqa: BLE001
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
