from .government import GovernmentParser, news_id_from_url
from .pravo import PravoParser, eo_from_url
from .regulation import RegulationParser, project_id_from_url
from .sozd import SozdParser, bill_number_from_url

__all__ = [
    "GovernmentParser",
    "PravoParser",
    "RegulationParser",
    "SozdParser",
    "bill_number_from_url",
    "eo_from_url",
    "news_id_from_url",
    "project_id_from_url",
    "fetch_npa_url",
]


def fetch_npa_url(url: str):
    host = (url or "").lower()
    if "regulation.gov.ru" in host:
        return RegulationParser().fetch_url(url)
    if "sozd.duma.gov.ru" in host:
        return SozdParser().fetch_url(url)
    if "publication.pravo.gov.ru" in host or "pravo.gov.ru/document" in host:
        return PravoParser().fetch_url(url)
    if "government.ru" in host:
        return GovernmentParser().fetch_url(url)
    return None
