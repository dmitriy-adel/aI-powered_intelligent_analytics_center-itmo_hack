
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
 
from psycopg2.extras import Json
 
 
# ---------------------------------------------------------------------
# Маппинги enum'ов БД <-> текст, который видит пользователь
# ---------------------------------------------------------------------
 
STATUS_DB_TO_API = {"active": "Активен", "paused": "Пауза", "error": "Ошибка"}
STATUS_API_TO_DB = {v: k for k, v in STATUS_DB_TO_API.items()}
 
PRIORITY_DB_TO_API = {"low": "Низкий", "mid": "Средний", "high": "Высокий"}
PRIORITY_API_TO_DB = {v: k for k, v in PRIORITY_DB_TO_API.items()}
 
# sources.source_type ('СМИ' | 'Регулятор' | 'Telegram') -> группа в сайдбаре.
# Значения самого source_type уже используются как поле "type" в ответе API
# без изменений — трансформировать нужно только "Регулятор" -> "Регуляторы".
TYPE_TO_GROUP = {"СМИ": "СМИ", "Регулятор": "Регуляторы", "Telegram": "Telegram"}
GROUP_TO_TYPE = {v: k for k, v in TYPE_TO_GROUP.items()}
GROUP_ORDER = ["СМИ", "Регуляторы", "Telegram"]
 
 
def status_to_api(db_value: Optional[str]) -> str:
    return STATUS_DB_TO_API.get(db_value, db_value or "Активен")
 
 
def status_to_db(api_value: Optional[str]) -> Optional[str]:
    return STATUS_API_TO_DB.get(api_value)
 
 
def priority_to_api(db_value: Optional[str]) -> Optional[str]:
    return PRIORITY_DB_TO_API.get(db_value)
 
 
def priority_to_db(api_value: Optional[str]) -> Optional[str]:
    return PRIORITY_API_TO_DB.get(api_value, "mid")
 
 
def group_for_type(source_type: str) -> str:
    return TYPE_TO_GROUP.get(source_type, source_type)
 
 
def type_for_group(group: Optional[str], fallback_type: Optional[str] = None) -> str:
    if fallback_type in TYPE_TO_GROUP:
        return fallback_type
    return GROUP_TO_TYPE.get(group or "", "СМИ")
 
 
# ---------------------------------------------------------------------
# Дата/время -> человекочитаемая строка ("10 мин. назад", "Вчера, 14:20")
# ---------------------------------------------------------------------
 
def humanize_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
 
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
 
    seconds = max(0.0, (now - dt).total_seconds())
    local_dt = dt.astimezone()
    local_now = now.astimezone()
    days_diff = (local_now.date() - local_dt.date()).days
 
    if seconds < 60:
        return "только что"
    if seconds < 3600:
        return f"{int(seconds // 60)} мин. назад"
    if days_diff == 0:
        return f"Сегодня, {local_dt:%H:%M}"
    if days_diff == 1:
        return f"Вчера, {local_dt:%H:%M}"
    if days_diff < 7:
        return f"{days_diff} дн. назад"
    return f"{local_dt:%d.%m.%Y}"
 
 
# ---------------------------------------------------------------------
# Текст -> число абзацев (для поля Paragraphs)
# ---------------------------------------------------------------------
 
def count_paragraphs(text: Optional[str]) -> int:
    if not text or not text.strip():
        return 1
    parts = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if len(parts) > 1:
        return len(parts)
    # Текста без пустых строк-разделителей — грубо считаем по предложениям.
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    return max(1, len(sentences))
 
 
# ---------------------------------------------------------------------
# JSONB-обёртки: три "факта" публикации (Кто/Что/Последствия и т.п.)
# хранятся как простые JSON-строки в jsonb-колонках.
# ---------------------------------------------------------------------
 
def to_jsonb(value: Optional[str]):
    if value is None or value == "":
        return None
    return Json(value)
 
 
def from_jsonb(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)
 
 
# ---------------------------------------------------------------------
# Генератор динамических UPDATE-запросов для частичного обновления
# ---------------------------------------------------------------------
 
def build_update_query(
    table: str,
    id_column: str,
    id_value: Any,
    fields: dict,
    allowed: Iterable[str],
    returning: str = "*",
):
    """Собирает `UPDATE <table> SET col=%s, ... WHERE id_column=%s RETURNING ...`
    только по тем ключам из `fields`, что входят в `allowed` и не None.
    Возвращает (query, params) или None, если обновлять нечего."""
    allowed_set = set(allowed)
    updates = {k: v for k, v in fields.items() if k in allowed_set and v is not None}
    if not updates:
        return None
 
    set_clause = ", ".join(f"{col} = %s" for col in updates)
    query = f"UPDATE {table} SET {set_clause} WHERE {id_column} = %s RETURNING {returning};"
    params = tuple(updates.values()) + (id_value,)
    return query, params
 
 
def unique_placeholder_url(prefix: str = "manual") -> str:
    """URL для новостей, добавленных вручную без ссылки на оригинал —
    колонка news.url NOT NULL UNIQUE, поэтому пустая строка не подходит."""
    import uuid
    return f"local://{prefix}/{uuid.uuid4().hex}"