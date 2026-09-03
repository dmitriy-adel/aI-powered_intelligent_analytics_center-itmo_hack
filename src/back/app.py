
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
 
from db_connection import DBConnection
import schemas
 
app = FastAPI(title="Аналитический центр — API")
 
# Пока фронтенд и API могут разворачиваться на разных портах во время
# разработки (например, Django раздаёт статику на 8080, а этот сервис
# слушает 8000) — открываем CORS широко. Для продакшена стоит сузить
# allow_origins до конкретного домена сайта.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
 
db = DBConnection()
 
 
@app.on_event("startup")
def on_startup():
    db.connect()
    db.ensure_schema()
 
 
@app.on_event("shutdown")
def on_shutdown():
    db.close()
 
 
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Фронтенд (api.js) читает текст ошибки из поля "error", а не из
    # стандартного FastAPI-поля "detail" — приводим формат к контракту.
    # rollback() тут на случай, если до HTTPException уже случилась ошибка
    # SQL-запроса: без отката соединение зависает в состоянии "aborted
    # transaction" и валит вообще все последующие запросы до перезапуска.
    db.rollback()
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
 
 
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    db.rollback()
    return JSONResponse(status_code=500, content={"error": f"Внутренняя ошибка сервера: {exc}"})
 
 
def _parse_source_id(raw: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Некорректный id источника: {raw!r}")
 
 
def _parse_news_id(raw: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Некорректный id публикации: {raw!r}")
 
 
# ---------------------------------------------------------------------
# Источники
# ---------------------------------------------------------------------
 
@app.get("/get_sources", response_model=schemas.GetSourcesResponse)
def get_sources():
    return {"sources": db.get_sources_grouped()}
 
 
@app.post("/add_source", response_model=schemas.AddSourceResponse, status_code=201)
def add_source(payload: schemas.AddSourceRequest):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Поле name обязательно")
    try:
        source = db.add_source(
            name=payload.name.strip(),
            url=(payload.url or "").strip(),
            group=payload.group,
            source_type=payload.type,
            category_default=payload.category or "Экономика",
            poll_interval=payload.poll_interval or "Каждые 15 минут",
        )
    except Exception as exc:  # UNIQUE-конфликт по name/url_rss и т.п.
        raise HTTPException(status_code=400, detail=f"Не удалось добавить источник: {exc}")
    return {"source": source}
 
 
@app.post("/change_source", response_model=schemas.ChangeSourceResponse)
def change_source(payload: schemas.ChangeSourceRequest):
    source_id = _parse_source_id(payload.id)
    updated = db.update_source(source_id, payload.model_dump(exclude={"id"}))
    if updated is None:
        raise HTTPException(status_code=404, detail="Источник не найден")
    return {"source": updated}
 
 
@app.post("/remove_source", response_model=schemas.OkResponse)
def remove_source(payload: schemas.RemoveSourceRequest):
    source_id = _parse_source_id(payload.id)
    if not db.remove_source(source_id):
        raise HTTPException(status_code=404, detail="Источник не найден")
    return {"ok": True}
 
 
# ---------------------------------------------------------------------
# Публикации
# ---------------------------------------------------------------------
 
@app.get("/get_news", response_model=schemas.GetNewsResponse)
def get_news(source: str = "general"):
    if source == "general":
        news = db.get_news_general()
    elif source == "manual":
        news = db.get_news_manual()
    else:
        source_id = _parse_source_id(source)
        news = db.get_news_by_source(source_id)
        if news is None:
            raise HTTPException(status_code=404, detail="Источник не найден")
    return {"source": source, "news": news}
 
 
@app.post("/add_news", response_model=schemas.AddNewsResponse, status_code=201)
def add_news(payload: schemas.AddNewsRequest):
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Поле title обязательно")
    try:
        news = db.add_news(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Не удалось добавить публикацию: {exc}")
    return {"news": news}
 
 
@app.post("/change_news", response_model=schemas.ChangeNewsResponse)
def change_news(payload: schemas.ChangeNewsRequest):
    news_id = _parse_news_id(payload.id)
    updated = db.update_news(news_id, payload.model_dump(exclude={"id"}))
    if updated is None:
        raise HTTPException(status_code=404, detail="Публикация не найдена")
    return {"news": updated}
 
 
@app.post("/remove_news", response_model=schemas.OkResponse)
def remove_news(payload: schemas.RemoveNewsRequest):
    news_id = _parse_news_id(payload.id)
    if not db.remove_news(news_id):
        raise HTTPException(status_code=404, detail="Публикация не найдена")
    return {"ok": True}
 