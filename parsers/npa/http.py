from typing import Optional

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}


def session(headers: Optional[dict] = None) -> requests.Session:
    sess = requests.Session()
    sess.headers.update(headers or HEADERS)
    return sess


def get_xml_text(el, default: str = "") -> str:
    if el is None or el.text is None:
        return default
    return (el.text or "").strip()
