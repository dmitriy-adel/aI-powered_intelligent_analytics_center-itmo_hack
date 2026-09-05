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


_add_to_syspath(BACK_DIR)
_add_to_syspath(RELEVANCE_DIR)
from db_connection import DBConnection  
from relevance_detector import RelevanceDetector  


def _load_module(unique_name: str, file_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(unique_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = module
    spec.loader.exec_module(module)
    
    return module


def _load_parsers():
    _add_to_syspath(PARSERS_DIR / "tg")
    tg_main = _load_module("tg_main", PARSERS_DIR / "tg" / "main.py")

    _add_to_syspath(PARSERS_DIR / "web")
    web_main = _load_module("web_main", PARSERS_DIR / "web" / "main.py")

    _add_to_syspath(ROOT)
    from parsers.npa import fetch as npa_fetch  # noqa: PLC0415

    return tg_main, web_main, npa_fetch


def main() -> None:
    tg_main, web_main, npa_fetch = _load_parsers()
    detector = RelevanceDetector()

    with DBConnection() as db:
        try:
            tg_main.main(db=db, detector=detector)

        except Exception as _ex:
            log.exception(f"something goes wrong while parsing TG :: {_ex}")

        try:
            web_main.main(db=db, detector=detector)

        except Exception as _ex:
            log.exception(f"something goes wrong while parsing web :: {_ex}")

        try:
            npa_fetch.collect_and_store(db=db, detector=detector)

        except Exception as _ex:
            log.exception(f"something goes wrong while parsing NPA :: {_ex}")

    log.info("all parsers finished theyr work")


if __name__ == "__main__":
    main()
