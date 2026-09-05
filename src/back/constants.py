_SOURCE_SELECT = """
    SELECT s.id, s.name, s.url, s.url_rss, s.source_type, s.status,
            s.last_update_dt, s.category_default, s.poll_interval,
            COUNT(n.id) FILTER (WHERE NOT n.is_hidden) AS news_count
    FROM sources s
    LEFT JOIN news n ON n.source_id = s.id
"""

NPA_SOURCES: dict[str, dict[str, str]] = {
    "government.ru": {
        "name": "Правительство РФ (government.ru)",
        "url": "https://government.ru",
    },
    "publication.pravo.gov.ru": {
        "name": "Официальное опубликование правовых актов (pravo.gov.ru)",
        "url": "http://publication.pravo.gov.ru",
    },
    "regulation.gov.ru": {
        "name": "Федеральный портал проектов НПА (regulation.gov.ru)",
        "url": "https://regulation.gov.ru",
    },
    "sozd.duma.gov.ru": {
        "name": "Госдума — СОЗД (sozd.duma.gov.ru)",
        "url": "https://sozd.duma.gov.ru",
    },
}

_NEWS_SELECT = """
    SELECT n.id, n.source_id, n.source, n.title, n.url, n.author,
        n.category, n.priority, n.description, n.lifetime, n.created_at,
        n.company_mentions, n.regulatory_changes, n.fact_when, n.consequences,
        n.tags, n.in_general, n.is_hidden, n.text,
        s.name AS source_display_name,
        e.object_id, e.object_type, e.events AS entity_events,
        CASE
            WHEN n.entity_id IS NULL THEN 1
            ELSE (
            SELECT COUNT(*)::int FROM news nx
            WHERE nx.entity_id = n.entity_id AND NOT nx.is_hidden
            )
        END AS plot_count,
        n.relevance_score
    FROM news n
    LEFT JOIN sources s ON s.id = n.source_id
    LEFT JOIN entities e ON e.id = n.entity_id
"""

STATUS_DB_TO_API = {"active": "Активен", "paused": "Пауза", "error": "Ошибка"}
STATUS_API_TO_DB = {v: k for k, v in STATUS_DB_TO_API.items()}
 
PRIORITY_DB_TO_API = {"low": "Низкий", "mid": "Средний", "high": "Высокий"}
PRIORITY_API_TO_DB = {v: k for k, v in PRIORITY_DB_TO_API.items()}
 
TYPE_TO_GROUP = {"СМИ": "СМИ", "Регулятор": "Регуляторы", "Telegram": "Telegram"}
GROUP_TO_TYPE = {v: k for k, v in TYPE_TO_GROUP.items()}