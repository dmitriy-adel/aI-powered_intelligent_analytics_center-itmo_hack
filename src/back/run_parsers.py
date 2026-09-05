import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType

ROOT: Path = Path(__file__).resolve().parents[2]
PARSERS_DIR: Path = ROOT / "parsers"
BACK_DIR: Path = Path(__file__).resolve().parent
RELEVANCE_DIR: Path = BACK_DIR / "relevance_detection"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("run_parsers")


def _add_to_syspath(path: Path) -> None:
    p = str(path)
    if p not in sys.path:
        sys.path.insert(0, p)


def _load_module(unique_name: str, file_path: Path) -> ModuleType:
    """
    Грузит модуль по прямому пути под уникальным именем. Обязательно, потому
    что и parsers/tg/main.py, и parsers/web/main.py называются "main" —
    обычный `import main` перепутал бы их через общий кэш sys.modules.
    """
    spec = importlib.util.spec_from_file_location(unique_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = module
    spec.loader.exec_module(module)
    return module


def _load_parsers():
    """
    tg/main.py и web/main.py используют "голые" импорты своих соседних
    модулей (tg_parser.py, web_parsers.py) — рассчитаны на запуск
    `python main.py` из своей же директории, где Python сам добавляет её
    в sys.path. При импорте как модуля так не происходит, поэтому
    добавляем директории парсеров в sys.path вручную перед загрузкой.
    db_connection и relevance_detector сами добавляют себе путь до src/back
    при импорте (см. верх каждого main.py) — здесь для них ничего делать не нужно.
    """
    _add_to_syspath(PARSERS_DIR / "tg")
    tg_main = _load_module("tg_main", PARSERS_DIR / "tg" / "main.py")

    _add_to_syspath(PARSERS_DIR / "web")
    web_main = _load_module("web_main", PARSERS_DIR / "web" / "main.py")

    _add_to_syspath(ROOT)
    from parsers.npa import fetch as npa_fetch  # noqa: PLC0415

    return tg_main, web_main, npa_fetch


def main() -> None:
    _add_to_syspath(BACK_DIR)
    _add_to_syspath(RELEVANCE_DIR)
    from db_connection import DBConnection  # noqa: PLC0415
    from relevance_detector import RelevanceDetector  # noqa: PLC0415

    tg_main, web_main, npa_fetch = _load_parsers()

    # Тяжёлая инициализация (NER, TF-IDF) — один раз на весь прогон, шарим
    # между всеми тремя парсерами вместо переинициализации в каждом.
    log.info("Инициализирую RelevanceDetector")
    detector = RelevanceDetector()

    # Одно соединение на весь прогон для tg/npa (однопоточные). web работает
    # через ThreadPoolExecutor по одному потоку на источник — psycopg2-
    # соединение нельзя делить между потоками, поэтому там process_source
    # по-прежнему открывает своё соединение на каждый источник; общий db
    # здесь используется только для начального чтения списка источников.
    with DBConnection() as db:
        log.info("=== TG-парсер ===")
        try:
            tg_main.main(db=db, detector=detector)
        except Exception:
            log.exception("TG-парсер завершился с ошибкой")

        log.info("=== Web-парсер ===")
        try:
            web_main.main(db=db, detector=detector)
        except Exception:
            log.exception("Web-парсер завершился с ошибкой")

        log.info("=== NPA-парсер ===")
        try:
            npa_fetch.collect_and_store(db=db, detector=detector)
        except Exception:
            log.exception("NPA-парсер завершился с ошибкой")

    log.info("Все парсеры завершены")


if __name__ == "__main__":
    main()
