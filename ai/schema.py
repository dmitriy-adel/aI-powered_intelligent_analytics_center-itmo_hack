ANNOTATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "document_type",
        "factual_title",
        "category",
        "importance",
        "summary",
        "who",
        "what",
        "when",
        "consequences",
        "tags",
        "relevance_to_company",
        "company_impact",
        "excel",
    ],
    "properties": {
        "document_type": {
            "type": "string",
            "enum": ["news", "regulation", "announcement"],
            "description": "news — отраслевая новость; regulation — НПА/закон; announcement — анонс меры без текста закона",
        },
        "factual_title": {
            "type": "string",
            "description": "Заголовок без кликбейта: что фактически произошло, 8–14 слов",
        },
        "category": {
            "type": "string",
            "enum": ["Политика", "Экономика", "Технологии", "Регулирование", "Общество"],
        },
        "importance": {
            "type": "string",
            "enum": ["Высокий", "Средний", "Низкий"],
            "description": "Потенциальная значимость для GS Labs, не для всего рынка",
        },
        "summary": {
            "type": "string",
            "description": "2–4 предложения: суть материала",
        },
        "who": {
            "type": "string",
            "description": "Ключевые субъекты через запятую",
        },
        "what": {
            "type": "string",
            "description": "Суть события одной фразой",
        },
        "when": {
            "type": "string",
            "description": "Сроки, даты, стадия — или «не указано»",
        },
        "consequences": {
            "type": "string",
            "description": "Возможные последствия для отрасли и/или GS Labs",
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 8,
        },
        "relevance_to_company": {
            "type": "string",
            "enum": ["noise", "low", "medium", "high"],
            "description": "noise — не про бизнес GS Labs; high — прямое влияние",
        },
        "company_impact": {
            "type": "string",
            "description": "1–2 предложения: касается ли GS Labs и как; если noise — почему шум",
        },
        "excel": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "essence",
                "applicability_score",
                "urgency_score",
                "relevance_score",
                "actuality_category",
            ],
            "properties": {
                "essence": {
                    "type": "string",
                    "description": "Поле «Суть / содержание» как в Excel-реестре",
                },
                "applicability_score": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 3,
                    "description": "К1 / Н2: применимость к GS Labs",
                },
                "urgency_score": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 3,
                    "description": "К6 / Н1: срочность или актуальность",
                },
                "relevance_score": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 3,
                    "description": "Н3: масштаб для отрасли",
                },
                "actuality_category": {
                    "type": "string",
                    "enum": ["На заметку", "Актуально", "Горячая тема", "Шум"],
                },
                "stage": {
                    "type": "string",
                    "description": "Стадия для НПА или «—» для новости",
                },
            },
        },
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["claim", "quote"],
                "properties": {
                    "claim": {"type": "string"},
                    "quote": {"type": "string"},
                },
            },
        },
    },
}
