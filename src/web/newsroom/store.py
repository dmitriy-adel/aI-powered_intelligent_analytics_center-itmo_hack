"""
Хранилище-заглушка "в памяти" для прототипа.

Настоящий бэкенд (парсеры источников + БД) появится позже — на этом этапе
важно, чтобы фронтенд и контракт API были готовы и проверены. Как только
реальный сбор данных будет готов, эти функции нужно заменить на обращения
к БД, сохранив сигнатуры (то, что они принимают и возвращают).

Схема публикации отдаёт по контракту как минимум:
    Source, Title, Link, Author, Category, Description, Published, Paragraphs
Остальные поля (importance, who/what/when/consequences, tags, ...) —
задел на будущее: фронтенд показывает их, только если они присутствуют,
и ничего не ломает, если бэкенд их пока не отдаёт.
"""

import itertools
from datetime import datetime

_order_counter = itertools.count(1)


def _next_order():
    return next(_order_counter)


def _news_item(
    source_id,
    source_name,
    title,
    link,
    category,
    description,
    pub_date,
    author="—",
    importance=None,
    who=None,
    what=None,
    when=None,
    consequences=None,
    tags=None,
    in_general=False,
    added_manually=False,
    added_by=None,
    mention_source=None,
):
    return {
        "id": f"n{_next_order():05d}",
        "source": source_id,
        "source_name": source_name,
        "title": title,
        "link": link,
        "author": author,
        "category": category,
        "importance": importance,
        "description": description,
        "pub_date": pub_date,
        "paragraphs": max(1, len(description.split(". "))),
        "who": who,
        "what": what,
        "when": when,
        "consequences": consequences,
        "tags": tags or [],
        "in_general": in_general,
        "added_manually": added_manually,
        "added_by": added_by,
        "mention_source": mention_source,
        "hidden": False,
        "_order": _next_order(),
    }


SOURCES = {
    "rbc": {
        "id": "rbc", "name": "РБК", "group": "СМИ", "type": "СМИ",
        "url": "rbc.ru/rss/partner/line...", "status": "Активен",
        "last_fetch": "10 мин. назад", "category_default": "Экономика",
        "poll_interval": "Каждые 15 минут",
    },
    "kommersant": {
        "id": "kommersant", "name": "Коммерсантъ", "group": "СМИ", "type": "СМИ",
        "url": "kommersant.ru/xml/list...", "status": "Активен",
        "last_fetch": "25 мин. назад", "category_default": "Экономика",
        "poll_interval": "Каждые 15 минут",
    },
    "vedomosti": {
        "id": "vedomosti", "name": "Ведомости", "group": "СМИ", "type": "СМИ",
        "url": "vedomosti.ru/news/rss", "status": "Пауза",
        "last_fetch": "3 ч. назад", "category_default": "Экономика",
        "poll_interval": "Каждый час",
    },
    "cbr": {
        "id": "cbr", "name": "ЦБ РФ", "group": "Регуляторы", "type": "Регулятор",
        "url": "cbr.ru/press/rss", "status": "Активен",
        "last_fetch": "1 ч. назад", "category_default": "Политика",
        "poll_interval": "Каждый час",
    },
    "fas": {
        "id": "fas", "name": "ФАС", "group": "Регуляторы", "type": "Регулятор",
        "url": "fas.gov.ru/news/xml", "status": "Ошибка",
        "last_fetch": "Вчера, 18:20", "category_default": "Регулирование",
        "poll_interval": "Каждый час",
    },
    "markettwits": {
        "id": "markettwits", "name": "@markettwits", "group": "Telegram", "type": "Telegram",
        "url": "t.me/markettwits", "status": "Активен",
        "last_fetch": "5 мин. назад", "category_default": "Экономика",
        "poll_interval": "Каждые 15 минут",
    },
    "banksta": {
        "id": "banksta", "name": "@banksta", "group": "Telegram", "type": "Telegram",
        "url": "t.me/banksta", "status": "Активен",
        "last_fetch": "12 мин. назад", "category_default": "Экономика",
        "poll_interval": "Каждые 15 минут",
    },
}

NEWS = {source_id: [] for source_id in SOURCES}
MANUAL_NEWS = []


def _seed():
    NEWS["rbc"].extend([
        _news_item(
            "rbc", "РБК",
            "ЦБ РФ рассматривает повышение ключевой ставки до 19% на ближайшем заседании",
            "https://rbc.ru/finances/example-1", "Экономика",
            "На фоне сохраняющегося высокого инфляционного давления и темпов кредитования "
            "Банк России может пойти на дальнейшее ужесточение денежно-кредитной политики. "
            "Большинство аналитиков сходятся во мнении, что шаг составит не менее 100 б.п.",
            "Сегодня, 14:20", importance="Высокий",
            who="Банк России (ЦБ РФ), Аналитики рынка",
            what="Повышение ключевой ставки до 19% годовых",
            when="Заседание совета директоров 13 сентября",
            consequences="Увеличение стоимости заемного финансирования, рост доходности по депозитам, охлаждение спроса",
            tags=["ЦБ РФ", "Ключевая ставка", "Инфляция", "ДКП"], in_general=True,
        ),
        _news_item(
            "rbc", "РБК",
            "Утвержден новый состав межведомственной комиссии по внешнеэкономическому сотрудничеству",
            "https://rbc.ru/politics/example-2", "Политика",
            "Правительство расширило полномочия комиссии по координации совместных проектов "
            "со странами БРИКС. В обновленный состав вошли представители Минпромторга, "
            "Минэкономразвития и ключевых госкорпораций.",
            "Сегодня, 12:05", importance="Средний",
            who="Правительство РФ, Комиссия по ВЭД, Страны БРИКС",
            what="Расширение полномочий координационного органа",
            when="Сентябрь 2024 года",
            consequences="Ускорение согласования совместных инвестиционных проектов и упрощение валютных расчетов",
            tags=["Правительство РФ", "ВЭД", "БРИКС", "Инвестиции"],
        ),
        _news_item(
            "rbc", "РБК",
            "Отечественные разработчики СУБД зафиксировали двукратный рост спроса со стороны госсектора",
            "https://rbc.ru/technology/example-3", "Технологии",
            "Крупнейшие ведомства форсируют переход на российские решения в рамках стратегии "
            "импортозамещения критической информационной инфраструктуры. Лидерами роста стали "
            "продукты на базе PostgreSQL.",
            "Вчера, 18:30", importance="Средний",
            who="Минцифры РФ, Разработчики СУБД, Госзаказчики",
            what="Переход госучреждений на отечественные СУБД",
            when="В течение 2024 года",
            consequences="Полный отказ от решений Oracle и Microsoft в КИИ к концу 2025 года",
            tags=["Импортозамещение", "ПО", "СУБД", "КИИ"],
        ),
        _news_item(
            "rbc", "РБК",
            "Роскомнадзор обновил методические рекомендации по маркировке интернет-рекламы",
            "https://rbc.ru/technology/example-4", "Регулирование",
            "Разъяснения касаются сложных форматов саморекламы и интеграций в прямых трансляциях. "
            "Ведомство уточнило критерии, по которым информационные сообщения не признаются рекламными.",
            "Вчера, 10:15", importance="Низкий",
            who="Роскомнадзор, Рекламодатели, Блогеры",
            what="Обновление методических указаний по маркировке",
            when="Вступают в силу с момента публикации",
            consequences="Снижение рисков наложения штрафов за отсутствие маркировки в спорных медиаформатах",
            tags=["Маркировка рекламы", "Законодательство", "Роскомнадзор"],
        ),
        _news_item(
            "rbc", "РБК",
            "ФАС России возбудила дело в отношении крупного металлургического холдинга из-за монопольных цен",
            "https://rbc.ru/business/example-5", "Регулирование",
            "Антимонопольная служба установила факты необоснованного повышения отпускных цен на "
            "арматуру и горячекатаный прокат на внутреннем рынке. Ведомство требует вернуть цены "
            "к экономически обоснованному уровню.",
            "Сегодня, 13:40", importance="Высокий",
            who="ФАС России, Металлургический комбинат",
            what="Возбуждение дела о нарушении закона о защите конкуренции",
            when="Проверка завершена 10 сентября",
            consequences="Возможные оборотные штрафы до 15% от годовой выручки, снижение цен на внутреннем рынке стройматериалов",
            tags=["ФАС", "Металлургия", "Антимонопольное регулирование", "Цены"],
            in_general=True, mention_source="РБК",
        ),
    ])

    NEWS["kommersant"].extend([
        _news_item(
            "kommersant", "Коммерсантъ",
            "Российские облачные провайдеры переходят на отечественное виртуализационное ПО",
            "https://kommersant.ru/example-1", "Технологии",
            "В связи с окончанием сроков действия лицензий зарубежного софта, крупнейшие "
            "дата-центры начали миграцию на платформы корпоративного уровня от российских разработчиков.",
            "Сегодня, 10:30", importance="Средний",
            who="Облачные провайдеры, Минцифры РФ",
            what="Миграция ИТ-инфраструктуры на отечественный софт",
            when="Процесс завершится к середине 2025 года",
            consequences="Повышение независимости от внешних вендоров, временные затраты на переобучение персонала",
            tags=["Облачные сервисы", "Виртуализация", "Импортозамещение"],
            in_general=True, mention_source="Коммерсантъ",
        ),
        _news_item(
            "kommersant", "Коммерсантъ",
            "Крупные работодатели переходят на четырехдневную рабочую неделю в пилотном режиме",
            "https://kommersant.ru/example-2", "Общество",
            "Эксперимент затронет офисных сотрудников нескольких ИТ-компаний, итоги подведут через полгода.",
            "Вчера, 14:00", importance="Средний",
            who="ИТ-компании, Сотрудники",
            what="Пилот четырехдневной рабочей недели",
            when="Старт с октября 2024 года",
            consequences="Возможный пересмотр трудового законодательства при успешных результатах",
            tags=["Труд", "HR", "Пилот"],
        ),
    ])

    NEWS["vedomosti"].extend([
        _news_item(
            "vedomosti", "Ведомости",
            "Промышленное производство в РФ выросло на 3,2% по итогам августа",
            "https://vedomosti.ru/example-1", "Экономика",
            "Росстат зафиксировал ускорение роста в обрабатывающих отраслях, в первую очередь за "
            "счет машиностроения и химической промышленности. Аналитики отмечают устойчивость "
            "показателя на фоне высокой ключевой ставки.",
            "Сегодня, 09:15", importance="Средний",
            who="Росстат, Минпромторг РФ",
            what="Рост индекса промышленного производства",
            when="Данные за август опубликованы 2 сентября",
            consequences="Пересмотр прогноза роста ВВП в сторону повышения, снижение давления на инфляцию со стороны предложения",
            tags=["Росстат", "Промышленность", "ВВП"],
        ),
        _news_item(
            "vedomosti", "Ведомости",
            "Минэкономразвития скорректировало методику расчета прожиточного минимума",
            "https://vedomosti.ru/example-2", "Регулирование",
            "Изменения затронут порядок индексации социальных выплат в регионах с высокой "
            "волатильностью цен на продукты первой необходимости.",
            "Вчера, 15:40", importance="Низкий",
            who="Минэкономразвития РФ, Регионы",
            what="Изменение методики расчета прожиточного минимума",
            when="Вступает в силу с 1 января 2025 года",
            consequences="Перерасчет социальных выплат в отдельных регионах",
            tags=["Минэкономразвития", "Соцвыплаты"],
        ),
        _news_item(
            "vedomosti", "Ведомости",
            "Крупный ритейлер сократил сроки доставки в регионах до одного дня",
            "https://vedomosti.ru/example-3", "Экономика",
            "Компания расширила сеть региональных распределительных центров и логистических хабов.",
            "3 дня назад", importance="Низкий",
            who="Ритейлер, Логистические партнеры",
            what="Сокращение сроков доставки",
            when="С сентября 2024 года",
            consequences="Рост онлайн-продаж в регионах",
            tags=["Ритейл", "Логистика"],
        ),
    ])

    NEWS["cbr"].extend([
        _news_item(
            "cbr", "ЦБ РФ",
            "Банк России сохранил жесткую риторику по денежно-кредитной политике",
            "https://cbr.ru/example-1", "Политика",
            "В пресс-релизе по итогам заседания регулятор подтвердил намерение удерживать ставку "
            "на повышенном уровне до устойчивого снижения инфляционных ожиданий.",
            "Сегодня, 13:05", importance="Высокий",
            who="Банк России",
            what="Публикация пресс-релиза по итогам заседания Совета директоров",
            when="13 сентября",
            consequences="Сохранение высокой стоимости заемных средств для бизнеса и населения",
            tags=["ЦБ РФ", "ДКП", "Пресс-релиз"],
        ),
        _news_item(
            "cbr", "ЦБ РФ",
            "ЦБ РФ расширил пилот цифрового рубля на новые категории операций",
            "https://cbr.ru/example-2", "Технологии",
            "К тестированию подключены дополнительные банки-партнеры, в пилоте появились сценарии "
            "оплаты услуг ЖКХ и государственных пошлин.",
            "Вчера, 11:20", importance="Средний",
            who="Банк России, Банки-партнеры",
            what="Расширение пилотного проекта цифрового рубля",
            when="С 1 октября 2024 года",
            consequences="Постепенный переход части безналичных расчетов на новую инфраструктуру",
            tags=["Цифровой рубль", "Банки", "Пилот"],
        ),
    ])

    NEWS["fas"].extend([
        _news_item(
            "fas", "ФАС",
            "ФАС утвердила новые правила недискриминационного доступа к электросетям",
            "https://fas.gov.ru/example-1", "Регулирование",
            "Документ регламентирует порядок технологического присоединения для новых промышленных "
            "потребителей и центров обработки данных.",
            "Вчера, 18:20", importance="Средний",
            who="ФАС России, Сетевые компании",
            what="Утверждение правил недискриминационного доступа",
            when="Приказ вступает в силу через 30 дней после публикации",
            consequences="Сокращение сроков подключения крупных потребителей к электросетям",
            tags=["ФАС", "Электросети", "Технологическое присоединение"],
        ),
        _news_item(
            "fas", "ФАС",
            "ФАС начала проверку ценообразования на рынке минеральных удобрений",
            "https://fas.gov.ru/example-2", "Регулирование",
            "Поводом стало резкое расхождение динамики внутренних и экспортных цен на фоне "
            "рекордного урожая зерновых.",
            "2 дня назад", importance="Высокий",
            who="ФАС России, Производители удобрений",
            what="Внеплановая проверка ценообразования",
            when="Результаты ожидаются в IV квартале",
            consequences="Возможное введение временных ограничений на экспортные цены",
            tags=["ФАС", "Удобрения", "Ценообразование"],
        ),
    ])

    NEWS["markettwits"].extend([
        _news_item(
            "markettwits", "@markettwits",
            "Рубль укрепился до 91,4 за доллар на фоне налогового периода",
            "https://t.me/markettwits/example-1", "Экономика",
            "Экспортеры нарастили продажу валютной выручки перед уплатой НДПИ и налога на прибыль.",
            "Сегодня, 11:02", importance="Средний",
            who="Экспортеры, Валютный рынок",
            what="Укрепление рубля",
            when="Торги 2 сентября",
            consequences="Временное снижение цен на импортные товары",
            tags=["Рубль", "Курс", "Налоговый период"],
        ),
        _news_item(
            "markettwits", "@markettwits",
            "Крупный ритейлер тестирует биометрическую оплату в 200 магазинах",
            "https://t.me/markettwits/example-2", "Технологии",
            "Пилот проходит в Москве и Санкт-Петербурге, средний чек по оплате лицом вырос на 12% "
            "относительно карточных платежей.",
            "Вчера, 20:11", importance="Низкий",
            who="Ритейлер, Покупатели",
            what="Расширение пилота биометрической оплаты",
            when="До конца 2024 года",
            consequences="Ускорение очередей на кассах, рост интереса к биометрии со стороны других сетей",
            tags=["Биометрия", "Ритейл", "Платежи"],
        ),
    ])

    NEWS["banksta"].extend([
        _news_item(
            "banksta", "@banksta",
            "Один из топ-20 банков столкнулся с оттоком корпоративных клиентов после смены тарифов",
            "https://t.me/banksta/example-1", "Регулирование",
            "Часть клиентов перешла к конкурентам после повышения комиссий за эквайринг и РКО для "
            "среднего бизнеса.",
            "Сегодня, 08:40", importance="Средний",
            who="Топ-20 банк, Корпоративные клиенты",
            what="Отток клиентов после изменения тарифной политики",
            when="Август-сентябрь 2024 года",
            consequences="Пересмотр тарифной политики, риски снижения комиссионных доходов",
            tags=["Банки", "Тарифы", "Эквайринг"],
        ),
        _news_item(
            "banksta", "@banksta",
            "Банки нарастили выдачу льготной ипотеки в регионах на 18%",
            "https://t.me/banksta/example-2", "Экономика",
            "Рост связан с расширением семейной ипотечной программы на вторичное жилье в малых городах.",
            "3 дня назад", importance="Низкий",
            who="Банки, Заемщики",
            what="Рост выдачи льготной ипотеки",
            when="Данные за август",
            consequences="Поддержка спроса на жилье в регионах, риски роста долговой нагрузки населения",
            tags=["Ипотека", "Льготные программы", "Банки"],
        ),
    ])

    MANUAL_NEWS.extend([
        _news_item(
            "manual", "Ручной ввод",
            "Минфин предлагает скорректировать параметры демпфирующего механизма для нефтяников",
            "https://minfin.gov.ru/ru/press-center", "Экономика",
            "Параметры демпфирующего механизма будут скорректированы в сторону уменьшения выплат. "
            "Решение направлено на балансировку государственного бюджета в условиях санкционного давления.",
            "Только что", importance="Высокий",
            who="Минфин РФ, Минэнерго, Нефтяные экспортеры",
            what="Поправки в формулу топливного демпфера",
            when="Рассмотрение в Госдуме в октябре",
            consequences="Корректировка маржинальности нефтепереработки, риски изменения оптовых цен на бензин АИ-95",
            tags=["Минфин РФ", "Топливный демпфер", "Налоги", "Бюджет"],
            in_general=True, added_manually=True, added_by="Иван Петров",
        ),
        _news_item(
            "manual", "Ручной ввод",
            "Правительство выделит дополнительные 15 млрд рублей на гранты молодым ученым",
            "https://government.ru/news", "Общество",
            "Средства направят на поддержку прикладных исследований в области микроэлектроники, "
            "генетики и материаловедения. Получатели грантов будут определяться по результатам "
            "всероссийского конкурса.",
            "Вчера, 16:50", importance="Средний",
            who="Минобрнауки РФ, Молодые ученые, ВУЗы",
            what="Субсидирование прикладных научных разработок",
            when="Выплаты начнутся в I квартале 2025 года",
            consequences="Стимулирование инновационной активности, удержание высококвалифицированных специалистов в стране",
            tags=["Наука", "Гранты", "Господдержка", "Молодые ученые"],
            in_general=True, added_manually=True, added_by="Мария Сидорова",
        ),
    ])


_seed()


# ---------------------------------------------------------------------------
# Источники — helpers
# ---------------------------------------------------------------------------

def list_sources():
    grouped = {}
    for source in SOURCES.values():
        count = len([n for n in NEWS.get(source["id"], []) if not n["hidden"]])
        entry = dict(source)
        entry["count"] = count
        grouped.setdefault(source["group"], []).append(entry)
    general_count = len(_general_news())
    return {
        "general_count": general_count,
        "groups": [
            {"name": group_name, "sources": sources}
            for group_name, sources in grouped.items()
        ],
    }


def _slugify(name):
    base = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    base = base or "source"
    candidate = base
    i = 2
    while candidate in SOURCES:
        candidate = f"{base}-{i}"
        i += 1
    return candidate


def add_source(name, group, source_type, url, category_default, poll_interval):
    source_id = _slugify(name)
    source = {
        "id": source_id, "name": name, "group": group, "type": source_type,
        "url": url, "status": "Активен", "last_fetch": "только что",
        "category_default": category_default, "poll_interval": poll_interval,
    }
    SOURCES[source_id] = source
    NEWS[source_id] = []
    return dict(source, count=0)


def update_source(source_id, fields):
    source = SOURCES.get(source_id)
    if source is None:
        return None
    for key in ("name", "group", "type", "url", "status", "category_default", "poll_interval"):
        if key in fields and fields[key] is not None:
            source[key] = fields[key]
    if fields.get("action") == "toggle":
        source["status"] = "Пауза" if source["status"] == "Активен" else "Активен"
    count = len([n for n in NEWS.get(source_id, []) if not n["hidden"]])
    return dict(source, count=count)


def remove_source(source_id):
    if source_id not in SOURCES:
        return False
    del SOURCES[source_id]
    NEWS.pop(source_id, None)
    return True


# ---------------------------------------------------------------------------
# Публикации — helpers
# ---------------------------------------------------------------------------

def _general_news():
    items = list(MANUAL_NEWS)
    for source_id, items_list in NEWS.items():
        items.extend(n for n in items_list if n["in_general"])
    items = [n for n in items if not n["hidden"]]
    return sorted(items, key=lambda n: n["_order"], reverse=True)


def list_news(source_id):
    if source_id == "general":
        return _general_news()
    if source_id == "manual":
        return sorted([n for n in MANUAL_NEWS if not n["hidden"]], key=lambda n: n["_order"], reverse=True)
    if source_id not in NEWS:
        return None
    return sorted(
        [n for n in NEWS[source_id] if not n["hidden"]],
        key=lambda n: n["_order"], reverse=True,
    )


def _all_lists():
    yield MANUAL_NEWS
    for items_list in NEWS.values():
        yield items_list


def add_news(payload):
    source_id = payload.get("source") or payload.get("Source") or "manual"
    source_name = SOURCES.get(source_id, {}).get("name", "Ручной ввод")
    added_manually = source_id == "manual" or bool(payload.get("added_manually"))

    item = _news_item(
        source_id=source_id,
        source_name=source_name,
        title=payload.get("title") or payload.get("Title") or "",
        link=payload.get("link") or payload.get("Link") or "",
        category=payload.get("category") or payload.get("Category") or "Экономика",
        description=payload.get("description") or payload.get("Description") or "",
        pub_date=payload.get("pub_date") or payload.get("Published") or "Только что",
        author=payload.get("author") or payload.get("Author") or "—",
        importance=payload.get("importance") or payload.get("priority"),
        tags=payload.get("tags") or [],
        in_general=bool(payload.get("in_general", True)),
        added_manually=added_manually,
        added_by=payload.get("added_by") or ("Иван Петров" if added_manually else None),
    )

    if source_id == "manual" or source_id not in NEWS:
        MANUAL_NEWS.append(item)
    else:
        NEWS[source_id].append(item)
    return item


def _find_news(news_id):
    for items_list in _all_lists():
        for item in items_list:
            if item["id"] == news_id:
                return item
    return None


def update_news(news_id, fields):
    item = _find_news(news_id)
    if item is None:
        return None
    editable = (
        "title", "link", "category", "description", "pub_date", "author",
        "importance", "who", "what", "when", "consequences", "tags",
        "in_general", "hidden",
    )
    for key in editable:
        if key in fields and fields[key] is not None:
            item[key] = fields[key]
    return item


def remove_news(news_id):
    for items_list in _all_lists():
        for i, item in enumerate(items_list):
            if item["id"] == news_id:
                del items_list[i]
                return True
    return False
