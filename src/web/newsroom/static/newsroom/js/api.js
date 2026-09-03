// Обёртка над fetch для эндпоинтов бэкенда.
//
// window.NEWSROOM_CONFIG.apiBase пустой по умолчанию — запросы идут на тот
// же origin, что и сама страница (т.е. когда бэкенд поднят как часть этого
// же Django-проекта на http://localhost:8000, всё работает "из коробки").
// Если API вынесут на отдельный домен/порт — просто впиши его сюда,
// например: apiBase: "http://localhost:8000".

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return decodeURIComponent(parts.pop().split(";").shift());
  return null;
}

async function apiRequest(path, { method = "GET", params, body } = {}) {
  const base = (window.NEWSROOM_CONFIG && window.NEWSROOM_CONFIG.apiBase) || "";
  let url = base + path;
  if (params) {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")
    ).toString();
    if (qs) url += `?${qs}`;
  }

  const headers = { "Content-Type": "application/json" };
  if (method !== "GET") {
    const token = getCookie("csrftoken") || (window.NEWSROOM_CONFIG && window.NEWSROOM_CONFIG.csrfToken);
    if (token) headers["X-CSRFToken"] = token;
  }

  const response = await fetch(url, {
    method,
    headers,
    credentials: "same-origin",
    body: body ? JSON.stringify(body) : undefined,
  });

  let data = null;
  try { data = await response.json(); } catch (_) { /* пустой ответ */ }

  if (!response.ok) {
    const message = (data && data.error) || `Ошибка запроса (${response.status})`;
    throw new Error(message);
  }
  return data;
}

const Api = {
  getSources: () => apiRequest("/get_sources"),
  getNews: (sourceId) => apiRequest("/get_news", { params: { source: sourceId } }),
  addNews: (payload) => apiRequest("/add_news", { method: "POST", body: payload }),
  changeNews: (payload) => apiRequest("/change_news", { method: "POST", body: payload }),
  removeNews: (id) => apiRequest("/remove_news", { method: "POST", body: { id } }),
  addSource: (payload) => apiRequest("/add_source", { method: "POST", body: payload }),
  changeSource: (payload) => apiRequest("/change_source", { method: "POST", body: payload }),
  removeSource: (id) => apiRequest("/remove_source", { method: "POST", body: { id } }),
};
