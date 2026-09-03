import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCEL_PATH = ROOT / "Для_ИТМО_мониторинг_НПА_и_отрасли.xlsx"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

DEFAULT_CARD_NUMBERS = [1, 2, 22, 23, 41, 28, 46, 11, 8, 3]


def _load_shared_strings(z: zipfile.ZipFile) -> list[str]:
    shared = []
    if "xl/sharedStrings.xml" not in z.namelist():
        return shared
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    for si in root.findall(f".//{NS}si"):
        parts = [t.text or "" for t in si.iter(f"{NS}t")]
        shared.append("".join(parts))
    return shared


def _cell_value(cell, shared: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    value_el = cell.find(f"{NS}v")
    if value_el is None or value_el.text is None:
        return ""
    if cell_type == "s":
        return shared[int(value_el.text)]
    return value_el.text


def _read_sheet(z: zipfile.ZipFile, sheet_idx: int, shared: list[str]) -> list[list[str]]:
    root = ET.fromstring(z.read(f"xl/worksheets/sheet{sheet_idx}.xml"))
    rows = []
    for row in root.findall(f".//{NS}sheetData/{NS}row"):
        rows.append([_cell_value(c, shared) for c in row.findall(f"{NS}c")])
    return rows


def _parse_npa_like(rows: list[list[str]], *, sheet_kind: str) -> dict[int, dict]:
    by_num = {}
    for row in rows[3:]:
        if not row or not row[0].strip().isdigit():
            continue
        num = int(row[0].strip())
        identifier = row[1] if len(row) > 1 else ""
        doc_type = row[2] if len(row) > 2 else ""
        stage = row[3] if len(row) > 3 else ""
        source_url = row[4] if len(row) > 4 else ""
        essence = row[15] if len(row) > 15 else ""
        by_num[num] = {
            "excel_no": num,
            "sheet": sheet_kind,
            "source": "Excel / GS Labs",
            "title": identifier,
            "link": source_url,
            "author": "—",
            "category": None,
            "description": essence,
            "pub_date": stage,
            "document_type_hint": "regulation" if sheet_kind == "npa" else "announcement",
            "excel_meta": {
                "тип_документа": doc_type,
                "стадия": stage,
                "к1": row[5] if len(row) > 5 else "",
                "итоговая_категория": row[14] if len(row) > 14 else "",
            },
            "text": (
                f"Тип материала: {doc_type}\n"
                f"Стадия: {stage}\n"
                f"Источник: {source_url}\n\n"
                f"Суть материала:\n{essence}"
            ),
            "paragraphs": [p for p in essence.split(". ") if p.strip()],
        }
    return by_num


def _parse_news(rows: list[list[str]]) -> dict[int, dict]:
    by_num = {}
    for row in rows[3:]:
        if not row or not row[0].strip().isdigit():
            continue
        num = int(row[0].strip())
        event = row[1] if len(row) > 1 else ""
        event_type = row[2] if len(row) > 2 else ""
        period = row[3] if len(row) > 3 else ""
        source_url = row[4] if len(row) > 4 else ""
        essence = row[11] if len(row) > 11 else ""
        by_num[num] = {
            "excel_no": num,
            "sheet": "news",
            "source": "Excel / GS Labs",
            "title": event,
            "link": source_url,
            "author": "—",
            "category": None,
            "description": essence,
            "pub_date": period,
            "document_type_hint": "news",
            "excel_meta": {
                "тип": event_type,
                "период": period,
                "н2_релевантность": row[6] if len(row) > 6 else "",
                "категория_актуальности": row[10] if len(row) > 10 else "",
            },
            "text": (
                f"Тип события: {event_type}\n"
                f"Период: {period}\n"
                f"Источник: {source_url}\n\n"
                f"Суть события:\n{essence}"
            ),
            "paragraphs": [p for p in essence.split(". ") if p.strip()],
        }
    return by_num


def load_excel_index() -> dict[int, dict]:
    with zipfile.ZipFile(EXCEL_PATH) as z:
        shared = _load_shared_strings(z)
        npa = _parse_npa_like(_read_sheet(z, 2, shared), sheet_kind="npa")
        projects = _parse_npa_like(_read_sheet(z, 3, shared), sheet_kind="projects")
        news = _parse_news(_read_sheet(z, 4, shared))
    return {**npa, **projects, **news}


if __name__ == "__main__":
    out = ROOT / "ai" / "output" / "excel_sample_10.json"
    index = load_excel_index()
    missing = [n for n in DEFAULT_CARD_NUMBERS if n not in index]
    if missing:
        raise KeyError(f"Карточки не найдены в Excel: {missing}")
    cards = [index[n] for n in DEFAULT_CARD_NUMBERS]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(cards)} cards -> {out}")
    for c in cards:
        print(f"  #{c['excel_no']} [{c['sheet']}] {c['title'][:60]}")
