"""
Аналитический центр — вьюхи страницы и заглушки API.

Все данные хранятся в памяти процесса (см. store.py) и сбрасываются при
перезапуске сервера. Это осознанное упрощение для этапа прототипа: как
только появится настоящий сбор новостей, эти вьюхи меняются на реальную
работу с БД/парсерами, а контракт (пути и поля JSON) можно оставить тем же.

Эндпоинты:
    GET  /get_sources                  -> список источников, сгруппированных по категориям
    GET  /get_news?source=<id>         -> список публикаций источника ('general' — общая лента)
    POST /add_news                     -> добавить публикацию (вручную или от источника)
    POST /change_news                  -> частичное обновление публикации по id
    POST /remove_news                  -> удалить публикацию по id
    POST /add_source                   -> добавить источник
    POST /change_source                -> обновить источник (в т.ч. вкл/выкл сбор)
    POST /remove_source                -> удалить источник
"""

import json

from django.shortcuts import render
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from . import store


@ensure_csrf_cookie
def index(request):
    """Единственная HTML-страница. Дальше всё живёт на клиенте: сайдбар,
    переключение лент и страница источников подгружаются через fetch."""
    return render(request, "newsroom/index.html")


def _parse_json_body(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------------------
# Источники
# ---------------------------------------------------------------------------

@require_GET
def get_sources(request):
    return JsonResponse({"sources": store.list_sources()})


@require_POST
def add_source(request):
    payload = _parse_json_body(request)
    if payload is None:
        return HttpResponseBadRequest("invalid json")

    name = (payload.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "Поле name обязательно"}, status=400)

    source = store.add_source(
        name=name,
        group=payload.get("group") or "СМИ",
        source_type=payload.get("type") or payload.get("group") or "СМИ",
        url=payload.get("url") or "",
        category_default=payload.get("category") or "Экономика",
        poll_interval=payload.get("poll_interval") or "Каждые 15 минут",
    )
    return JsonResponse({"source": source}, status=201)


@require_POST
def change_source(request):
    payload = _parse_json_body(request)
    if payload is None:
        return HttpResponseBadRequest("invalid json")

    source_id = payload.get("id")
    if not source_id:
        return JsonResponse({"error": "Поле id обязательно"}, status=400)

    updated = store.update_source(source_id, payload)
    if updated is None:
        return JsonResponse({"error": "Источник не найден"}, status=404)
    return JsonResponse({"source": updated})


@require_POST
def remove_source(request):
    payload = _parse_json_body(request)
    if payload is None:
        return HttpResponseBadRequest("invalid json")

    source_id = payload.get("id")
    if not source_id:
        return JsonResponse({"error": "Поле id обязательно"}, status=400)

    ok = store.remove_source(source_id)
    if not ok:
        return JsonResponse({"error": "Источник не найден"}, status=404)
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# Публикации
# ---------------------------------------------------------------------------

@require_GET
def get_news(request):
    source_id = request.GET.get("source", "general")
    news = store.list_news(source_id)
    if news is None:
        return JsonResponse({"error": "Источник не найден"}, status=404)
    return JsonResponse({"source": source_id, "news": news})


@require_POST
def add_news(request):
    payload = _parse_json_body(request)
    if payload is None:
        return HttpResponseBadRequest("invalid json")

    title = (payload.get("title") or payload.get("Title") or "").strip()
    if not title:
        return JsonResponse({"error": "Поле title обязательно"}, status=400)

    item = store.add_news(payload)
    return JsonResponse({"news": item}, status=201)


@require_POST
def change_news(request):
    payload = _parse_json_body(request)
    if payload is None:
        return HttpResponseBadRequest("invalid json")

    news_id = payload.get("id")
    if not news_id:
        return JsonResponse({"error": "Поле id обязательно"}, status=400)

    updated = store.update_news(news_id, payload)
    if updated is None:
        return JsonResponse({"error": "Публикация не найдена"}, status=404)
    return JsonResponse({"news": updated})


@require_POST
def remove_news(request):
    payload = _parse_json_body(request)
    if payload is None:
        return HttpResponseBadRequest("invalid json")

    news_id = payload.get("id")
    if not news_id:
        return JsonResponse({"error": "Поле id обязательно"}, status=400)

    ok = store.remove_news(news_id)
    if not ok:
        return JsonResponse({"error": "Публикация не найдена"}, status=404)
    return JsonResponse({"ok": True})
