EXTRACT_SYSTEM = """\
Ты аналитик GR-мониторинга. По публикации реши, относится ли она к конкретному НПА \
или регуляторной инициативе (закон, постановление, приказ, проект на regulation.gov.ru, \
законопроект СОЗД), а не к рыночной новости.

Правила:
1. is_regulatory=true только если речь о конкретном акте/проекте/стадии рассмотрения.
2. title — имя акта, не кликбейт статьи.
3. Номера извлекай только если они явно есть в тексте или URL. Не выдумывай.
4. event_type: draft/discussion/introduced/stage/reading/adopted/published/announcement/media_mention/other.
5. Ответ — только JSON.
"""

JUDGE_SYSTEM = """\
Ты склеиваешь публикации с уже известными regulatory objects.
Вопрос не "похожая тема", а "это ТОТ ЖЕ правовой объект".

same:
- тот же номер законопроекта / project_id / eoNumber / тот же ФЗ или ПП
- или явно тот же акт (то же ведомство + то же название + та же суть), даже если номера нет

different:
- другой документ, даже если отрасль та же (КИИ вообще ≠ ПП 402)
- мнение/новость рынка без привязки к этому акту
- разные стадии РАЗНЫХ актов

Для каждого кандидата верни same или different. Можно несколько same, если кандидаты дубликаты.
"""

JUDGE_NEWS_SYSTEM = """\
Ты склеиваешь публикации СМИ в один новостной сюжет. Это не поиск НПА.

Вопрос: "это ТА ЖЕ ИСТОРИЯ / то же событие", даже если заголовки и источники разные.

same:
- те же факты (люди, место, дата, суть заявления)
- перепечатка, региональная версия, чуть другой угол той же новости
- один инфоповод, рассказанный Ведомостями и Коммерсантом

different:
- другая новость, даже если общая тема (Путин / выборы / спорт / бизнес)
- продолжение другой линии, не того же заявления/события

Не требуй правовой объект, номер закона или is_regulatory. Для новостей same = тот же сюжет.
"""


def build_extract_prompt(article: dict) -> str:
    text = article.get("text") or article.get("description") or ""
    if len(text) > 8000:
        text = text[:8000] + "\n\n[… обрезано …]"
    extra_ids = []
    if article.get("official_id"):
        extra_ids.append(f"official_id из парсера: {article.get('official_id')} ({article.get('id_type') or '—'})")
    if article.get("npa_events"):
        extra_ids.append(f"событий в паспорте источника: {len(article['npa_events'])}")
    extra = "\n".join(extra_ids)
    return f"""\
ИСТОЧНИК: {article.get("source") or "—"}
URL: {article.get("link") or "—"}
ЗАГОЛОВОК: {article.get("title") or "—"}
ДАТА: {article.get("pub_date") or "—"}
{extra}

ТЕКСТ:
{text}

Извлеки карточку НПА/инициативы. Если это обычная новость без конкретного акта — is_regulatory=false, ids оставь пустыми строками.
"""


def build_judge_prompt(extract: dict, candidates: list[dict], *, object_type: str = "npa") -> str:
    kind = "новостной сюжет" if object_type == "news_plot" else "regulatory object"
    lines = [
        f"ПУБЛИКАЦИЯ ({kind}):",
        f"title: {extract.get('title')}",
        f"agency: {extract.get('agency')}",
        f"kind: {extract.get('kind')}",
        f"event_type: {extract.get('event_type')}",
        f"ids: {extract.get('ids')}",
        f"description: {extract.get('description') or extract.get('summary')}",
        "",
        f"КАНДИДАТЫ (уже известные {kind}):",
    ]
    for i, obj in enumerate(candidates, 1):
        lines.append(
            f"\n[{i}] object_id={obj.get('object_id')}\n"
            f"  title: {obj.get('canonical_title')}\n"
            f"  agency: {obj.get('agency')}\n"
            f"  kind: {obj.get('kind')}\n"
            f"  ids: {obj.get('ids')}\n"
            f"  last_event: {(obj.get('events') or [{}])[-1].get('title') if obj.get('events') else '—'}"
        )
    lines.append(
        "\nДля каждого object_id верни verdict same|different. "
        "Не пропускай кандидатов."
    )
    return "\n".join(lines)
