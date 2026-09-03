SYSTEM_PROMPT = """\
Ты аналитик мониторинга для GS Labs (ООО "Цифра") — российского разработчика ПО \
для цифрового ТВ, OTT, CAS/DRM. Продукты компании в Едином реестре российского ПО.

Задача: по тексту публикации заполнить структурированную карточку для PR/GR-специалиста.

Правила:
1. factual_title — НЕ переписывай кликбейт. Напиши, что РЕАЛЬНО произошло: субъект + действие + объект. \
Без "шок", "сенсация", вопросительных заголовков, намёков.
2. Не выдумывай факты, которых нет в тексте. Если данных мало — так и напиши.
3. importance и relevance_to_company оценивай для GS Labs, не "важность новости вообще". \
Новости про агро/медицину без связи с IT — noise.
4. category — одна из пяти UI-категорий. regulation/announcement → чаще "Регулирование".
5. excel.applicability_score (0–3): 0 не применимо, 3 прямое влияние на продукты/реестр/телеком.
6. excel.urgency_score (0–3): 0 >12 мес, 3 уже действует или <1 мес.
7. company_impact: если relevance noise — объясни одной фразой, почему не про компанию.
8. Отвечай только JSON по схеме, на русском языке.
"""


def build_user_prompt(article: dict, company_profile: dict) -> str:
    facts = "\n".join(f"- {f}" for f in company_profile.get("facts", []))
    topics = ", ".join(company_profile.get("monitoring_topics", []))
    unknown = ", ".join(company_profile.get("unknown_facts", []))

    text = article.get("text") or article.get("description") or ""
    if len(text) > 12000:
        text = text[:12000] + "\n\n[… текст обрезан …]"

    return f"""\
КОНТЕКСТ КОМПАНИИ: {company_profile.get("company_name")}
Отрасль: {company_profile.get("industry")}
Продукты: {", ".join(company_profile.get("products", []))}
Факты:
{facts}
Темы мониторинга: {topics}
Неизвестно (не предполагай): {unknown}

ИСТОЧНИК: {article.get("source", "—")}
ОРИГИНАЛЬНЫЙ ЗАГОЛОВОК (может быть кликбейтным): {article.get("title", "—")}
ССЫЛКА: {article.get("link", "—")}
ДАТА: {article.get("pub_date", "—")}

ТЕКСТ:
{text}

Заполни карточку. factual_title обязан отличаться от оригинального заголовка, \
если оригинал кликбейтный или неинформативный.
"""
