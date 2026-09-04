EXTRACT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "is_regulatory",
        "title",
        "agency",
        "event_type",
        "description",
        "ids",
        "kind",
        "stage",
        "confidence",
    ],
    "properties": {
        "is_regulatory": {
            "type": "boolean",
            "description": "Это НПА, проект НПА или регуляторная инициатива (не отраслевая новость рынка)",
        },
        "title": {
            "type": "string",
            "description": "Каноническое название акта/инициативы, не заголовок статьи",
        },
        "agency": {
            "type": "string",
            "description": "Орган: ГД, Правительство, Минцифры, ФСТЭК, … или пусто",
        },
        "event_type": {
            "type": "string",
            "enum": [
                "draft",
                "discussion",
                "introduced",
                "stage",
                "reading",
                "adopted",
                "published",
                "announcement",
                "media_mention",
                "other",
            ],
        },
        "description": {
            "type": "string",
            "description": "1–3 предложения: что произошло с этим актом",
        },
        "kind": {
            "type": "string",
            "description": "законопроект / ФЗ / ПП / приказ / проект постановления / иное",
        },
        "stage": {
            "type": "string",
            "description": "Стадия, если указана, иначе пусто",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
        },
        "ids": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "sozd_bill",
                "regulation_project",
                "regulation_npa_id",
                "pravo_eo",
                "pp_number",
                "fz_number",
            ],
            "properties": {
                "sozd_bill": {
                    "type": "string",
                    "description": "Номер законопроекта СОЗД, например 1215252-8, иначе пусто",
                },
                "regulation_project": {
                    "type": "string",
                    "description": "Числовой id проекта regulation.gov.ru, иначе пусто",
                },
                "regulation_npa_id": {
                    "type": "string",
                    "description": "Полный projectId вида 02/07/10-25/00161889, иначе пусто",
                },
                "pravo_eo": {
                    "type": "string",
                    "description": "eoNumber publication.pravo.gov.ru, иначе пусто",
                },
                "pp_number": {
                    "type": "string",
                    "description": "Номер постановления Правительства без №, иначе пусто",
                },
                "fz_number": {
                    "type": "string",
                    "description": "Номер ФЗ, например 243-ФЗ, иначе пусто",
                },
            },
        },
    },
}

JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdicts"],
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["object_id", "verdict", "reason"],
                "properties": {
                    "object_id": {"type": "string"},
                    "verdict": {
                        "type": "string",
                        "enum": ["same", "different"],
                        "description": "same = та же правовая сущность, не «похожая тема»",
                    },
                    "reason": {"type": "string"},
                },
            },
        }
    },
}
