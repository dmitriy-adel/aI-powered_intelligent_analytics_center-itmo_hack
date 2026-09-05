async function apiRequest(path, { method = "GET", params, body } = {}) {
  let url = API_BASE + path;
  if (params) {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")
    ).toString();
    if (qs) url += `?${qs}`;
  }
 
  const response = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
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
