const state = {
  sources: null,          // ответ /get_sources
  view: { type: "feed", sourceId: "general" },
  newsCache: {},          // sourceId -> список публикаций
  filters: { search: "", category: "Все", importance: "Все", source: "Все" },
  tab: "news",             // "news" | "reports"
  reportType: "daily",     // "daily" | "weekly"
  reportsCache: {},        // `${sourceId}:${reportType}` -> список отчётов
};

const $main = document.getElementById("main");
const $sidebarScroll = document.getElementById("sidebar-scroll");
const $modalRoot = document.getElementById("modal-root");
const $toastStack = document.getElementById("toast-stack");

function escapeHtml(str) {
  return String(str ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

const EVENT_TYPE_LABEL = {
  introduced: "Внесён",
  draft: "Проект",
  discussion: "Обсуждение",
  reading: "Чтение",
  stage: "Стадия",
  published: "Опубликован",
  revision: "Правки",
  announcement: "Анонс",
};

function formatLifecycleDate(raw) {
  if (!raw) return "";
  const s = String(raw).trim();
  const iso = s.match(/^(\d{4}-\d{2}-\d{2})/);
  if (iso) {
    const [y, m, d] = iso[1].split("-");
    return `${d}.${m}.${y}`;
  }
  const ru = s.match(/^(\d{2}\.\d{2}\.\d{4})/);
  return ru ? ru[1] : s.slice(0, 16);
}

function orderedLifecycle(events) {
  const list = Array.isArray(events) ? events.slice() : [];
  if (!list.length) return [];
  const last = String(list[list.length - 1].event_type || "").toLowerCase();
  if (last === "introduced") list.reverse();
  return list;
}

function lifecycleHtml(events, { limit = 0 } = {}) {
  const all = orderedLifecycle(events);
  if (!all.length) return "";
  const shown = limit && all.length > limit ? all.slice(0, limit) : all;
  const more = all.length - shown.length;
  const items = shown.map((ev) => {
    const kind = EVENT_TYPE_LABEL[(ev.event_type || "").toLowerCase()] || ev.event_type || "Этап";
    const date = formatLifecycleDate(ev.date);
    const title = escapeHtml(ev.title || "");
    const inner = ev.link
      ? `<a href="${escapeHtml(ev.link)}" target="_blank" rel="noopener">${title}</a>`
      : title;
    return `<li class="timeline__item">
      <span class="timeline__dot"></span>
      <div>
        <div class="timeline__meta">${escapeHtml(kind)}${date ? ` · ${escapeHtml(date)}` : ""}</div>
        <div class="timeline__title">${inner}</div>
      </div>
    </li>`;
  }).join("");
  return `<ol class="timeline">${items}</ol>${more ? `<div class="timeline__more">ещё ${more} стадий — откройте карточку</div>` : ""}`;
}

function toast(message, type = "ok") {
  const el = document.createElement("div");
  el.className = "toast" + (type === "error" ? " toast--error" : "");
  el.textContent = message;
  $toastStack.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

const ICONS = {
  list: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M5.5 4h8M5.5 8h8M5.5 12h8M2.5 4h.01M2.5 8h.01M2.5 12h.01" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
  smi: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><rect x="2.5" y="3" width="11" height="10" rx="1.5" stroke="currentColor" stroke-width="1.4"/><path d="M5 6h6M5 8.3h6M5 10.6h3.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>',
  shield: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 2l5 1.8v3.7c0 3.2-2.1 5.6-5 6.5-2.9-.9-5-3.3-5-6.5V3.8L8 2Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M6 8l1.4 1.4L10.2 6.4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  telegram: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M2 8.4l11-4.4-2 10-3.4-2.7L6 13l.3-3.4 6-5.4-7.5 4.3-2.8-1Z" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/></svg>',
  edit: '<svg width="15" height="15" viewBox="0 0 15 15" fill="none"><path d="M9.4 2.6l3 3-7 7-3.3.5.4-3.3 6.9-7.2Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>',
  eyeOff: '<svg width="15" height="15" viewBox="0 0 15 15" fill="none"><path d="M2 2l11 11M6.4 6.6a2 2 0 002.9 2.9M4.2 4.4C2.7 5.3 1.6 6.6 1 7.5c1.4 2.4 4 4.5 6.5 4.5 1 0 2-.3 2.9-.9M11 4.1c1.2.9 2.2 2.1 3 3.4-.5.9-1.3 1.9-2.2 2.7" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  trash: '<svg width="15" height="15" viewBox="0 0 15 15" fill="none"><path d="M2.5 4h10M5.8 4V2.8c0-.4.4-.8.8-.8h1.8c.4 0 .8.4.8.8V4M6 6.7v4M9 6.7v4M3.5 4l.6 7.4c0 .6.5 1.1 1.1 1.1h5.6c.6 0 1-.5 1.1-1.1L12.5 4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  close: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2.5 2.5l9 9M11.5 2.5l-9 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
  play: '<svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M3.5 2.6v7.8l6.5-3.9-6.5-3.9Z" fill="currentColor"/></svg>',
  pause: '<svg width="13" height="13" viewBox="0 0 13 13" fill="none"><rect x="3" y="2.5" width="2.4" height="8" fill="currentColor"/><rect x="7.6" y="2.5" width="2.4" height="8" fill="currentColor"/></svg>',
  settings: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.3"/><path d="M8 1.5v1.6M8 12.9v1.6M14.5 8h-1.6M3.1 8H1.5M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1M12.6 12.6l-1.1-1.1M4.5 4.5L3.4 3.4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>',
  refresh: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M12.25 7A5.25 5.25 0 1 1 10.6 3.15M12.25 1.75V4.9H9.1" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  eye: '<svg width="15" height="15" viewBox="0 0 15 15" fill="none"><path d="M1 7.5c1.4-2.4 4-4.5 6.5-4.5s5.1 2.1 6.5 4.5c-1.4 2.4-4 4.5-6.5 4.5S2.4 9.9 1 7.5Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><circle cx="7.5" cy="7.5" r="2" stroke="currentColor" stroke-width="1.2"/></svg>',
};

function groupIcon(groupName) {
  if (groupName === "СМИ") return ICONS.smi;
  if (groupName === "Регуляторы") return ICONS.shield;
  if (groupName === "Telegram") return ICONS.telegram;
  return ICONS.list;
}

// ---------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------

async function init() {
  document.getElementById("btn-refresh-sources").addEventListener("click", () => loadSources(true));
  document.getElementById("btn-open-sources").addEventListener("click", () => openSourcesView());
  document.getElementById("btn-add-news").addEventListener("click", () => openAddNewsModal());

  $sidebarScroll.addEventListener("click", onSidebarClick);
  $main.addEventListener("click", onMainClick);
  $main.addEventListener("change", onMainChange);
  $main.addEventListener("input", onMainInput);
  $modalRoot.addEventListener("click", onModalClick);

  await loadSources();
  await openFeedView("general", "Общая лента");
}

async function loadSources(showToast = false) {
  try {
    const data = await Api.getSources();
    state.sources = data.sources;
    renderSidebar();
    if (showToast) toast("Список источников обновлён");
  } catch (err) {
    toast("Не удалось загрузить источники: " + err.message, "error");
  }
}

// ---------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------

function renderSidebar() {
  const activeId = state.view.type === "feed" ? state.view.sourceId : null;
  const generalCount = state.sources ? state.sources.general_count : "";

  let html = `
    <button class="nav-item ${activeId === "general" ? "is-active" : ""}" data-action="open-feed" data-source="general" data-name="Общая лента">
      <span class="nav-item__icon">${ICONS.list}</span>
      <span class="nav-item__label">Общая лента</span>
      <span class="nav-item__badge">${generalCount}</span>
    </button>
  `;

  if (state.sources) {
    for (const group of state.sources.groups) {
      html += `<div class="sidebar__section-title">${escapeHtml(group.name.toUpperCase())}</div>`;
      for (const src of group.sources) {
        const statusMeta = STATUS_META[src.status] || {};
        html += `
          <button class="nav-item ${activeId === src.id ? "is-active" : ""}" data-action="open-feed" data-source="${src.id}" data-name="${escapeHtml(src.name)}" data-group="${escapeHtml(group.name)}">
            <span class="nav-item__icon">${groupIcon(group.name)}</span>
            <span class="nav-item__label">${escapeHtml(src.name)}</span>
            ${src.status === "Ошибка" ? `<span class="nav-item__status-dot ${statusMeta.dot}" title="Ошибка сбора"></span>` : ""}
            <span class="nav-item__badge">${src.count}</span>
          </button>
        `;
      }
    }
  }

  $sidebarScroll.innerHTML = html;
}

function onSidebarClick(e) {
  const btn = e.target.closest("[data-action='open-feed']");
  if (!btn) return;
  openFeedView(btn.dataset.source, btn.dataset.name, btn.dataset.group);
}

// ---------------------------------------------------------------------
// Feed view (источник или общая лента)
// ---------------------------------------------------------------------

async function openFeedView(sourceId, sourceName, groupName) {
  state.view = { type: "feed", sourceId, sourceName, groupName };
  state.filters = { search: "", category: "Все", importance: "Все", source: "Все" };
  state.tab = "news";
  renderSidebar();
  renderFeedSkeleton(sourceName, sourceId);
  await loadNews(sourceId);
}
function renderFeedSkeleton(sourceName, sourceId) {
  const isGeneral = sourceId === "general";
  $main.innerHTML = `
    ${!isGeneral ? `<div class="main__breadcrumb"><a data-action="open-feed" data-source="general" data-name="Общая лента" href="javascript:void(0)">${escapeHtml(state.view.groupName || "")}</a> / ${escapeHtml(sourceName)}</div>` : ""}
    <div class="main__header">
      <div>
        <h1 class="h-xl">${isGeneral ? "Общая лента" : "Публикации " + escapeHtml(sourceName)}</h1>
        <p>${isGeneral ? "Отслеживаемые упоминания и добавленные публикации" : "Загружаем последние публикации источника…"}</p>
      </div>
      <button class="btn btn--secondary" type="button">${isGeneral ? "Настройка потоков" : "Экспорт ленты"}</button>
    </div>
    <div class="skeleton"></div>
    <div class="skeleton"></div>
    <div class="skeleton"></div>
  `;
}

async function loadNews(sourceId) {
  try {
    const data = await Api.getNews(sourceId);
    state.newsCache[sourceId] = data.news;
    renderFeed();
  } catch (err) {
    $main.innerHTML = `<div class="empty-state">Не удалось загрузить публикации: ${escapeHtml(err.message)}</div>`;
  }
}

function filteredNews() {
  const { sourceId } = state.view;
  const items = state.newsCache[sourceId] || [];
  const { search, category, importance, source } = state.filters;
  return items.filter((n) => {
    if (category !== "Все" && n.category !== category) return false;
    if (importance !== "Все" && n.importance && n.importance !== importance) return false;
    if (source !== "Все" && (n.mention_source || n.source_name) !== source) return false;
    if (search) {
      const haystack = (n.title + " " + n.description + " " + (n.tags || []).join(" ")).toLowerCase();
      if (!haystack.includes(search.toLowerCase())) return false;
    }
    return true;
  });
}

function mainTabsHtml() {
  return `
    <div class="tabs">
      <button class="tabs__item ${state.tab === "news" ? "is-active" : ""}" data-action="switch-tab" data-tab="news" type="button">Публикации</button>
      <button class="tabs__item ${state.tab === "reports" ? "is-active" : ""}" data-action="switch-tab" data-tab="reports" type="button">Отчёты</button>
    </div>
  `;
}

function renderFeed() {
  const { sourceId, sourceName, groupName } = state.view;
  const isGeneral = sourceId === "general";
  const items = filteredNews();
  const allItems = state.newsCache[sourceId] || [];

  const sourceOptions = isGeneral
    ? ["Все", ...new Set(allItems.map((n) => n.mention_source || n.source_name))]
    : null;

  $main.innerHTML = `
    ${!isGeneral ? `<div class="main__breadcrumb"><a data-action="open-feed" data-source="general" data-name="Общая лента" href="javascript:void(0)">${escapeHtml(groupName || "")}</a> / ${escapeHtml(sourceName)}</div>` : ""}
    <div class="main__header">
      <div>
        <h1 class="h-xl">${isGeneral ? "Общая лента" : "Публикации " + escapeHtml(sourceName)}</h1>
        <p>${isGeneral ? "Отслеживаемые упоминания и добавленные публикации" : `Всего публикаций: ${allItems.length}`}</p>
      </div>
      <button class="btn btn--secondary" type="button">${isGeneral ? "Настройка потоков" : "Экспорт ленты"}</button>
    </div>

    ${mainTabsHtml()}

    <div class="filters">
      <label class="filters__search">
        <svg width="15" height="15" viewBox="0 0 15 15" fill="none"><circle cx="6.5" cy="6.5" r="4.2" stroke="currentColor" stroke-width="1.3"/><path d="M9.6 9.6l3 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>
        <input type="text" id="filter-search" placeholder="Поиск по публикациям и сущностям…" value="${escapeHtml(state.filters.search)}">
      </label>
      ${isGeneral ? `
        <select id="filter-source">
          <option value="Все">Источник: Все</option>
          ${sourceOptions.filter((s) => s !== "Все").map((s) => `<option value="${escapeHtml(s)}" ${state.filters.source === s ? "selected" : ""}>${escapeHtml(s)}</option>`).join("")}
        </select>` : ""}
      <select id="filter-category">
        <option value="Все">Категория: Все</option>
        ${CATEGORY_OPTIONS.map((c) => `<option value="${c}" ${state.filters.category === c ? "selected" : ""}>${c}</option>`).join("")}
      </select>
      <select id="filter-importance">
        <option value="Все">Важность: Все</option>
        ${IMPORTANCE_OPTIONS.map((i) => `<option value="${i}" ${state.filters.importance === i ? "selected" : ""}>${i}</option>`).join("")}
      </select>
    </div>

    <div id="feed-list">
      ${items.length ? items.map((n) => newsCardHtml(n, isGeneral)).join("") : `
        <div class="empty-state">
          <div class="empty-state__icon">${ICONS.list}</div>
          <div class="h-m">Пока пусто</div>
          <p class="body-regular">Публикации появятся здесь после сбора данных источником${isGeneral ? " или добавления вручную" : ""}.</p>
        </div>`}
    </div>
  `;
}

// ---------------------------------------------------------------------
// Отчёты (вкладка внутри ленты)
// ---------------------------------------------------------------------

function formatDateShort(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function truncate(text, n) {
  if (!text) return "";
  return text.length > n ? text.slice(0, n).trim() + "…" : text;
}

function reportsCacheKey(sourceId, reportType) {
  return `${sourceId}:${reportType}`;
}

function renderReportsView() {
  const { sourceId, sourceName, groupName } = state.view;
  const isGeneral = sourceId === "general";
  const cacheKey = reportsCacheKey(sourceId, state.reportType);
  const reports = state.reportsCache[cacheKey];

  $main.innerHTML = `
    ${!isGeneral ? `<div class="main__breadcrumb"><a data-action="open-feed" data-source="general" data-name="Общая лента" href="javascript:void(0)">${escapeHtml(groupName || "")}</a> / ${escapeHtml(sourceName)}</div>` : ""}
    <div class="main__header">
      <div>
        <h1 class="h-xl">${isGeneral ? "Общая лента" : "Публикации " + escapeHtml(sourceName)}</h1>
        <p>Отчёты по этой ленте</p>
      </div>
      <button class="btn btn--secondary" type="button">${isGeneral ? "Настройка потоков" : "Экспорт ленты"}</button>
    </div>

    ${mainTabsHtml()}

    <div class="reports-toolbar">
      <div class="tabs tabs--pill">
        <button class="tabs__item ${state.reportType === "daily" ? "is-active" : ""}" data-action="switch-report-type" data-report-type="daily" type="button">Ежедневные</button>
        <button class="tabs__item ${state.reportType === "weekly" ? "is-active" : ""}" data-action="switch-report-type" data-report-type="weekly" type="button">Еженедельные</button>
      </div>
      <button class="btn btn--primary" data-action="generate-report" type="button">
        Сформировать ${state.reportType === "daily" ? "дневной" : "недельный"} отчёт
      </button>
    </div>

    ${state.reportType === "daily" ? `<p class="reports-hint">Показаны последние 7 дневных отчётов.</p>` : ""}

    <div id="reports-list">
      ${reports === undefined ? `<div class="skeleton"></div><div class="skeleton"></div>` : renderReportsListOnly(reports)}
    </div>
  `;

  if (reports === undefined) loadReports(sourceId, state.reportType);
}

function renderReportsListOnly(reports) {
  if (!reports.length) {
    return `
      <div class="empty-state">
        <div class="empty-state__icon">${ICONS.list}</div>
        <div class="h-m">Отчётов пока нет</div>
        <p class="body-regular">Нажмите «Сформировать», чтобы создать первый отчёт за ${state.reportType === "daily" ? "сегодня" : "эту неделю"}.</p>
      </div>`;
  }
  return reports.map(reportCardHtml).join("");
}

function reportCardHtml(r) {
  const periodLabel = r.report_type === "daily"
    ? formatDateShort(r.period_start)
    : `${formatDateShort(r.period_start)} – ${formatDateShort(r.period_end)}`;
  return `
    <article class="card" data-report-id="${r.id}">
      <div class="card__top">
        <div class="card__badges">
          <span class="badge">${r.report_type === "daily" ? "Ежедневный" : "Еженедельный"}</span>
          <span class="badge">${r.news_count} публикаций</span>
        </div>
        <span class="card__origin">${escapeHtml(periodLabel)}</span>
      </div>
      <h3 class="card__title" data-action="view-report">${escapeHtml(r.title)}</h3>
      <p class="card__desc">${escapeHtml(truncate(r.content, 220))}</p>
      <div class="card__footer">
        <div class="card__meta"><span>Сформирован ${escapeHtml(r.created_at)}</span></div>
        <div class="card__actions">
          <button class="icon-btn" data-action="view-report" title="Открыть">${ICONS.eye}</button>
        </div>
      </div>
    </article>
  `;
}

async function loadReports(sourceId, reportType) {
  try {
    const data = await Api.getReports(sourceId, reportType);
    state.reportsCache[reportsCacheKey(sourceId, reportType)] = data.reports;
    const listEl = document.getElementById("reports-list");
    if (listEl && state.view.sourceId === sourceId && state.tab === "reports" && state.reportType === reportType) {
      listEl.innerHTML = renderReportsListOnly(data.reports);
    }
  } catch (err) {
    const listEl = document.getElementById("reports-list");
    if (listEl) listEl.innerHTML = `<div class="empty-state">Не удалось загрузить отчёты: ${escapeHtml(err.message)}</div>`;
  }
}

async function generateReport() {
  const { sourceId } = state.view;
  const reportType = state.reportType;
  const btn = document.querySelector("[data-action='generate-report']");
  const originalLabel = btn ? btn.textContent : "";
  if (btn) { btn.disabled = true; btn.textContent = "Формирую…"; }

  try {
    const fn = reportType === "daily" ? Api.generateDailyReport : Api.generateWeeklyReport;
    const { report } = await fn(sourceId);
    const cacheKey = reportsCacheKey(sourceId, reportType);
    const withoutSamePeriod = (state.reportsCache[cacheKey] || []).filter(
      (r) => !(r.period_start === report.period_start && r.period_end === report.period_end)
    );
    const updated = [report, ...withoutSamePeriod];
    state.reportsCache[cacheKey] = reportType === "daily" ? updated.slice(0, 7) : updated;
    renderReportsView();
    toast("Отчёт сформирован");
  } catch (err) {
    toast("Не удалось сформировать отчёт: " + err.message, "error");
    if (btn) { btn.disabled = false; btn.textContent = originalLabel; }
  }
}

function openReportViewModal(report) {
  if (!report) return;
  const periodLabel = report.report_type === "daily"
    ? formatDateShort(report.period_start)
    : `${formatDateShort(report.period_start)} – ${formatDateShort(report.period_end)}`;

  $modalRoot.innerHTML = `
    <div class="modal-overlay">
      <div class="modal">
        <div class="modal__header">
          <h2 class="modal__title h-l">${escapeHtml(report.title)}</h2>
          <button class="modal__close" data-action="close-modal">${ICONS.close}</button>
        </div>

        <div class="modal__section">
          <div class="card__badges" style="margin-bottom:8px;">
            <span class="badge">${report.report_type === "daily" ? "Ежедневный" : "Еженедельный"}</span>
            <span class="badge">${report.news_count} публикаций</span>
          </div>
          <div style="color:var(--text-secondary, #6B7280); font-size:13px;">
            ${escapeHtml(periodLabel)} · сформирован ${escapeHtml(report.created_at)} · ${escapeHtml(report.source_name)}
          </div>
        </div>

        <div class="modal__section">
          <div style="max-height:400px; overflow-y:auto; white-space:pre-wrap; line-height:1.6;">${escapeHtml(report.content)}</div>
        </div>

        <div class="modal__footer">
          <button class="btn btn--secondary" data-action="close-modal">Закрыть</button>
        </div>
      </div>
    </div>
  `;
}

function newsCardHtml(n, isGeneral) {
  const facts = [
    ["Кто", n.who], ["Что", n.what], ["Когда", n.when], ["Последствия", n.consequences],
  ].filter(([, v]) => v);

  let originLabel = "";
  if (isGeneral) {
    if (n.added_manually) {
      originLabel = `<span class="card__origin card__origin--manual">Добавлено вручную — ${escapeHtml(n.added_by || "")}</span>`;
    } else if (n.mention_source) {
      originLabel = `<span class="card__origin card__origin--mention">Упоминание · ${escapeHtml(n.mention_source)}</span>`;
    } else {
      originLabel = `<span class="card__origin">${escapeHtml(n.source_name || "")}</span>`;
    }
  }

  return `
    <article class="card" data-news-id="${n.id}">
      <div class="card__top">
        <div class="card__badges">
          ${n.category ? `<span class="badge" style="${categoryStyle(n.category)}">${escapeHtml(n.category)}</span>` : ""}
          ${n.importance ? `<span class="badge" style="${importanceStyle(n.importance)}">${escapeHtml(n.importance)}</span>` : ""}
          ${n.object_type === "npa" ? `<span class="badge">НПА</span>` : ""}
          ${n.lifecycle && n.lifecycle.length > 1 ? `<span class="badge">${n.lifecycle.length} стадий</span>` : ""}
          ${isGeneral && n.plot_count > 1 ? `<span class="badge">${n.plot_count} источников</span>` : ""}
        </div>
        ${originLabel}
      </div>
      <h3 class="card__title" data-action="open-news">${escapeHtml(n.title)}</h3>
      <p class="card__desc">${escapeHtml(n.description)}</p>
      ${facts.length ? `
        <dl class="card__facts">
          ${facts.map(([k, v]) => `<dt>${k}:</dt><dd>${escapeHtml(v)}</dd>`).join("")}
        </dl>` : ""}
      ${n.lifecycle && n.lifecycle.length ? `
        <div class="timeline-wrap">
          <div class="timeline-wrap__label">Жизненный цикл</div>
          ${lifecycleHtml(n.lifecycle, { limit: 8 })}
        </div>` : ""}
      ${n.tags && n.tags.length ? `
        <div class="card__tags">${n.tags.map((t) => `<span class="card__tag">${escapeHtml(t)}</span>`).join("")}</div>` : ""}
      <div class="card__footer">
        <div class="card__meta">
          <span>${escapeHtml(n.pub_date || "")}</span>
          ${n.link ? `<a href="${escapeHtml(n.link)}" target="_blank" rel="noopener">Оригинал →</a>` : ""}
        </div>
        <div class="card__actions">
          <button class="icon-btn" data-action="hide-news" title="Скрыть из ленты">${ICONS.eyeOff}</button>
          <button class="icon-btn icon-btn--danger" data-action="delete-news" title="Удалить">${ICONS.trash}</button>
          <button class="icon-btn" data-action="view-news" title="Просмотр">${ICONS.eye}</button>
          <button class="icon-btn" data-action="open-news" title="Открыть / редактировать">${ICONS.edit}</button>
        </div>
      </div>
    </article>
  `;
}

function onMainInput(e) {
  if (e.target.id === "filter-search") {
    state.filters.search = e.target.value;
    document.getElementById("feed-list").innerHTML = renderFeedListOnly();
  }
}

function renderFeedListOnly() {
  const items = filteredNews();
  const isGeneral = state.view.sourceId === "general";
  return items.length ? items.map((n) => newsCardHtml(n, isGeneral)).join("") : `
    <div class="empty-state">
      <div class="empty-state__icon">${ICONS.list}</div>
      <div class="h-m">Ничего не найдено</div>
      <p class="body-regular">Попробуй изменить поиск или фильтры.</p>
    </div>`;
}

function onMainChange(e) {
  if (e.target.id === "filter-category") { state.filters.category = e.target.value; renderFeed(); }
  if (e.target.id === "filter-importance") { state.filters.importance = e.target.value; renderFeed(); }
  if (e.target.id === "filter-source") { state.filters.source = e.target.value; renderFeed(); }
}

async function onMainClick(e) {
  const openFeedBtn = e.target.closest("[data-action='open-feed']");
  if (openFeedBtn) { openFeedView(openFeedBtn.dataset.source, openFeedBtn.dataset.name); return; }

    const tabBtn = e.target.closest("[data-action='switch-tab']");
  if (tabBtn) {
    state.tab = tabBtn.dataset.tab;
    if (state.tab === "reports") renderReportsView(); else renderFeed();
    return;
  }

  const reportTypeBtn = e.target.closest("[data-action='switch-report-type']");
  if (reportTypeBtn) {
    state.reportType = reportTypeBtn.dataset.reportType;
    renderReportsView();
    return;
  }

  if (e.target.closest("[data-action='generate-report']")) {
    await generateReport();
    return;
  }

  const reportCard = e.target.closest("[data-report-id]");
  if (reportCard && e.target.closest("[data-action='view-report']")) {
    const cacheKey = reportsCacheKey(state.view.sourceId, state.reportType);
    const report = (state.reportsCache[cacheKey] || []).find((r) => r.id === reportCard.dataset.reportId);
    openReportViewModal(report);
    return;
  }

  const card = e.target.closest(".card");
  const newsId = card ? card.dataset.newsId : null;

  if (e.target.closest("[data-action='view-news']") && newsId) {
    openNewsViewModal(findNewsById(newsId));
    return;
  }

  if (e.target.closest("[data-action='open-news']") && newsId) {
    openNewsModal(findNewsById(newsId));
    return;
  }
  if (e.target.closest("[data-action='hide-news']") && newsId) {
    await hideNews(newsId);
    return;
  }
  if (e.target.closest("[data-action='delete-news']") && newsId) {
    if (confirm("Удалить эту публикацию? Действие необратимо.")) await deleteNews(newsId);
    return;
  }

  // Источники: действия в таблице
  const sourceRow = e.target.closest("[data-source-id]");
  if (sourceRow) {
    const sourceId = sourceRow.dataset.sourceId;
    if (e.target.closest("[data-action='toggle-source']")) { await toggleSource(sourceId); return; }
    if (e.target.closest("[data-action='delete-source']")) {
      if (confirm("Удалить источник и всю его историю публикаций?")) await deleteSource(sourceId);
      return;
    }
    if (e.target.closest("[data-action='edit-source']")) {
      toast("Редактирование источников появится позже — пока доступны запуск/пауза и удаление.");
      return;
    }
  }

  if (e.target.closest("#btn-add-source-focus")) {
    document.getElementById("quick-add-url")?.focus();
  }

  if (e.target.closest("#btn-quick-add-submit")) {
    submitQuickAddSource();
  }
}

function findNewsById(id) {
  for (const list of Object.values(state.newsCache)) {
    const found = list.find((n) => n.id === id);
    if (found) return found;
  }
  return null;
}

async function hideNews(id) {
  try {
    await Api.changeNews({ id, hidden: true });
    for (const list of Object.values(state.newsCache)) {
      const idx = list.findIndex((n) => n.id === id);
      if (idx !== -1) list.splice(idx, 1);
    }
    renderFeed();
    toast("Публикация скрыта из ленты");
  } catch (err) {
    toast("Не удалось скрыть публикацию: " + err.message, "error");
  }
}

async function deleteNews(id) {
  try {
    await Api.removeNews(id);
    for (const list of Object.values(state.newsCache)) {
      const idx = list.findIndex((n) => n.id === id);
      if (idx !== -1) list.splice(idx, 1);
    }
    renderFeed();
    await loadSources();
    toast("Публикация удалена");
  } catch (err) {
    toast("Не удалось удалить публикацию: " + err.message, "error");
  }
}

// ---------------------------------------------------------------------
// Модалка: детали / редактирование публикации
// ---------------------------------------------------------------------

function openNewsModal(n) {
  if (!n) return;
  $modalRoot.innerHTML = `
    <div class="modal-overlay">
      <div class="modal" data-news-id="${n.id}">
        <div class="modal__header">
          <h2 class="modal__title h-l">${n.object_type === "npa" ? "Цикл НПА" : "Детали публикации"}</h2>
          <button class="modal__close" data-action="close-modal">${ICONS.close}</button>
        </div>

        <div class="modal__section">
          <input class="field" id="edit-title" style="width:100%; padding:9px 12px; border:1px solid var(--border); border-radius:6px; font-weight:600;" value="${escapeHtml(n.title)}">
        </div>

        <div class="modal__grid-2">
          <div class="field">
            <label>Категория</label>
            <select id="edit-category">
              ${CATEGORY_OPTIONS.map((c) => `<option value="${c}" ${n.category === c ? "selected" : ""}>${c}</option>`).join("")}
            </select>
          </div>
          <div class="field">
            <label>Важность</label>
            <select id="edit-importance">
              ${IMPORTANCE_OPTIONS.map((i) => `<option value="${i}" ${n.importance === i ? "selected" : ""}>${i}</option>`).join("")}
            </select>
          </div>
        </div>

        ${n.text ? `
        <div class="field modal__section">
          <label>Текст новости (исходный, не редактируется)</label>
          <div style="max-height:220px; overflow-y:auto; white-space:pre-wrap; padding:9px 12px; border:1px solid var(--border); border-radius:6px; background:var(--bg-muted, #f7f7f8); color:var(--text-secondary, #555); font-size:14px; line-height:1.5;">${escapeHtml(n.text)}</div>
        </div>
        ` : ""}

        <div class="field modal__section">
          <label>Аннотация</label>
          <textarea id="edit-description" rows="4" style="width:100%; padding:9px 12px; border:1px solid var(--border); border-radius:6px; resize:vertical;">${escapeHtml(n.description)}</textarea>
        </div>

        <div class="modal__section">
          <div class="card__facts" style="margin-bottom:0;">
            <dt>Кто:</dt><dd><input id="edit-who" style="width:100%; border:1px solid var(--border); border-radius:6px; padding:6px 8px;" value="${escapeHtml(n.who || "")}"></dd>
            <dt>Что:</dt><dd><input id="edit-what" style="width:100%; border:1px solid var(--border); border-radius:6px; padding:6px 8px;" value="${escapeHtml(n.what || "")}"></dd>
            <dt>Когда:</dt><dd><input id="edit-when" style="width:100%; border:1px solid var(--border); border-radius:6px; padding:6px 8px;" value="${escapeHtml(n.when || "")}"></dd>
            <dt>Последствия:</dt><dd><input id="edit-consequences" style="width:100%; border:1px solid var(--border); border-radius:6px; padding:6px 8px;" value="${escapeHtml(n.consequences || "")}"></dd>
          </div>
        </div>

        ${n.lifecycle && n.lifecycle.length ? `
        <div class="modal__section">
          <div class="timeline-wrap__label">Жизненный цикл · ${n.lifecycle.length} стадий</div>
          ${lifecycleHtml(n.lifecycle)}
        </div>` : ""}

        <div class="toggle-row">
          <span>Добавлена в общую ленту · ${escapeHtml(n.pub_date || "")}</span>
          <label class="switch">
            <input type="checkbox" id="edit-in-general" ${n.in_general ? "checked" : ""}>
            <span class="switch__track"></span>
          </label>
        </div>

        <div class="modal__meta-row">
          <span>Источник: ${escapeHtml(n.source_name || "—")}</span>
          ${n.link ? `<a href="${escapeHtml(n.link)}" target="_blank" rel="noopener">Открыть оригинал →</a>` : ""}
        </div>

        <div class="modal__footer modal__footer--split">
          <button class="btn btn--danger-text" data-action="delete-from-modal">Удалить</button>
          <div style="display:flex; gap:8px;">
            <button class="btn btn--secondary" data-action="close-modal">Отменить</button>
            <button class="btn btn--primary" data-action="save-news">Сохранить</button>
          </div>
        </div>
      </div>
    </div>
  `;
}

async function onModalClick(e) {
  // Фон (.modal-overlay) НЕ несёт data-action="close-modal" — он есть только
  // на крестике и кнопках "Отменить"/"Отмена". Поэтому closest() отсюда
  // никогда случайно не всплывёт до фона при клике внутри .modal, и окно
  // закрывается только по явному намерению: клик по фону вне карточки или
  // по одной из этих кнопок.
  const clickedOverlayBackground = e.target.classList.contains("modal-overlay");
  const clickedCloseAction = e.target.closest("[data-action='close-modal']");
  if (clickedOverlayBackground || clickedCloseAction) {
    $modalRoot.innerHTML = "";
    return;
  }

  const modalEl = e.target.closest(".modal[data-news-id]");

  if (modalEl && e.target.closest("[data-action='edit-from-view']")) {
    openNewsModal(findNewsById(modalEl.dataset.newsId));
    return;
  }

  if (modalEl && e.target.closest("[data-action='save-news']")) {
    const id = modalEl.dataset.newsId;
    const fields = {
      id,
      title: document.getElementById("edit-title").value,
      category: document.getElementById("edit-category").value,
      importance: document.getElementById("edit-importance").value,
      description: document.getElementById("edit-description").value,
      who: document.getElementById("edit-who").value,
      what: document.getElementById("edit-what").value,
      when: document.getElementById("edit-when").value,
      consequences: document.getElementById("edit-consequences").value,
      in_general: document.getElementById("edit-in-general").checked,
    };
    try {
      const { news } = await Api.changeNews(fields);
      applyNewsUpdate(news);
      $modalRoot.innerHTML = "";
      renderFeed();
      toast("Изменения сохранены");
    } catch (err) {
      toast("Не удалось сохранить: " + err.message, "error");
    }
    return;
  }

  if (modalEl && e.target.closest("[data-action='delete-from-modal']")) {
    const id = modalEl.dataset.newsId;
    if (confirm("Удалить эту публикацию?")) {
      await deleteNews(id);
      $modalRoot.innerHTML = "";
    }
    return;
  }

  // Add-source / add-news modal submits handled in their own handlers below
}

function applyNewsUpdate(updated) {
  for (const list of Object.values(state.newsCache)) {
    const idx = list.findIndex((n) => n.id === updated.id);
    if (idx !== -1) list[idx] = updated;
  }
}

// ---------------------------------------------------------------------
// Модалка: добавить публикацию вручную
// ---------------------------------------------------------------------

function openAddNewsModal() {
  $modalRoot.innerHTML = `
    <div class="modal-overlay">
      <div class="modal" id="add-news-modal">
        <div class="modal__header">
          <h2 class="modal__title h-l">Добавить публикацию вручную</h2>
          <button class="modal__close" data-action="close-modal">${ICONS.close}</button>
        </div>

        <div class="field modal__section">
          <label>Заголовок</label>
          <input id="add-title" placeholder="Введите заголовок публикации…">
        </div>

        <div class="field modal__section">
          <label>Текст / Саммари</label>
          <textarea id="add-description" rows="4" placeholder="Краткое содержание публикации…"></textarea>
          <div style="margin-top:8px;">
            <button class="btn btn--secondary btn--sm" type="button" id="btn-generate-summary">✨ Сгенерировать саммари</button>
          </div>
        </div>

        <div class="modal__grid-2">
          <div class="field">
            <label>Категория</label>
            <select id="add-category">${CATEGORY_OPTIONS.map((c) => `<option value="${c}">${c}</option>`).join("")}</select>
          </div>
          <div class="field">
            <label>Важность</label>
            <select id="add-importance">${IMPORTANCE_OPTIONS.map((i) => `<option value="${i}">${i}</option>`).join("")}</select>
          </div>
        </div>

        <div class="field modal__section">
          <label>Теги</label>
          <div class="tag-input" id="add-tag-input">
            <input type="text" id="add-tag-field" placeholder="Добавить тег…">
          </div>
        </div>

        <div class="modal__grid-2">
          <div class="field">
            <label>Источник / ссылка</label>
            <input id="add-link" placeholder="https://…">
          </div>
          <div class="field">
            <label>Дата публикации</label>
            <input id="add-pub-date" type="date" value="${new Date().toISOString().slice(0, 10)}">
          </div>
        </div>

        <label class="checkbox-row modal__section">
          <input type="checkbox" id="add-in-general" checked>
          Сразу добавить в общую ленту
        </label>

        <div class="modal__footer">
          <button class="btn btn--secondary" data-action="close-modal">Отмена</button>
          <button class="btn btn--primary" id="btn-submit-news">Добавить публикацию</button>
        </div>
      </div>
    </div>
  `;

  const tags = [];
  const $tagInput = document.getElementById("add-tag-input");
  const $tagField = document.getElementById("add-tag-field");

  function renderTags() {
    $tagInput.querySelectorAll(".badge--chip").forEach((el) => el.remove());
    tags.forEach((t, i) => {
      const chip = document.createElement("span");
      chip.className = "badge badge--chip";
      chip.innerHTML = `${escapeHtml(t)} <button type="button" data-i="${i}">×</button>`;
      chip.querySelector("button").addEventListener("click", () => { tags.splice(i, 1); renderTags(); });
      $tagInput.insertBefore(chip, $tagField);
    });
  }

  $tagField.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && $tagField.value.trim()) {
      e.preventDefault();
      tags.push($tagField.value.trim());
      $tagField.value = "";
      renderTags();
    }
  });

  document.getElementById("btn-generate-summary").addEventListener("click", () => {
    // Заглушка ИИ-суммаризации: на этом этапе просто аккуратно обрезаем
    // введённый текст. Когда появится реальная генерация — заменить тело
    // этого обработчика на вызов соответствующего эндпоинта.
    const $desc = document.getElementById("add-description");
    const text = $desc.value.trim();
    if (!text) { toast("Сначала вставь текст публикации", "error"); return; }
    const summary = text.length > 220 ? text.slice(0, 217).trim() + "…" : text;
    $desc.value = summary;
    toast("Саммари сгенерировано (черновая заглушка)");
  });

  document.getElementById("btn-submit-news").addEventListener("click", async () => {
    const title = document.getElementById("add-title").value.trim();
    if (!title) { toast("Укажи заголовок публикации", "error"); return; }

    const payload = {
      title,
      description: document.getElementById("add-description").value.trim(),
      category: document.getElementById("add-category").value,
      importance: document.getElementById("add-importance").value,
      link: document.getElementById("add-link").value.trim(),
      pub_date: document.getElementById("add-pub-date").value,
      tags,
      in_general: document.getElementById("add-in-general").checked,
      source: "manual",
    };

    try {
      const { news } = await Api.addNews(payload);
      state.newsCache["manual"] = state.newsCache["manual"] || [];
      state.newsCache["manual"].unshift(news);
      if (state.newsCache["general"]) state.newsCache["general"].unshift(news);
      $modalRoot.innerHTML = "";
      await loadSources();
      if (state.view.type === "feed") renderFeed();
      toast("Публикация добавлена");
    } catch (err) {
      toast("Не удалось добавить публикацию: " + err.message, "error");
    }
  });
}

// ---------------------------------------------------------------------
// Страница управления источниками
// ---------------------------------------------------------------------

function openSourcesView() {
  state.view = { type: "sources" };
  renderSidebar();
  renderSourcesView();
}

function renderSourcesView() {
  const groups = (state.sources && state.sources.groups) || [];
  const allSources = groups.flatMap((g) => g.sources);

  $main.innerHTML = `
    <div class="main__breadcrumb">Настройки / Источники данных</div>
    <div class="main__header">
      <div><h1 class="h-xl">Управление источниками</h1></div>
      <button class="btn btn--primary" id="btn-add-source-focus" type="button">+ Добавить источник</button>
    </div>

    <div class="table-card">
      <table class="sources-table">
        <thead>
          <tr>
            <th>Название</th><th>Тип</th><th>URL источника</th><th>Статус</th>
            <th>Последний сбор</th><th>Действия</th>
          </tr>
        </thead>
        <tbody>
          ${allSources.map(sourceRowHtml).join("")}
        </tbody>
      </table>
    </div>

    <div class="quick-add">
      <h3 class="quick-add__title h-m">Быстрое добавление источника</h3>
      <p class="quick-add__hint body-regular">Введите адрес ресурса, чтобы система определила формат и настроила сбор данных</p>

      <div class="quick-add__row">
        <input type="text" id="quick-add-url" placeholder="URL или юзернейм канала">
      </div>

      <div class="quick-add__grid">
        <div class="field">
          <label>Тип источника</label>
          <select id="quick-add-type">${SOURCE_TYPE_OPTIONS.map((t) => `<option value="${t}">${t}</option>`).join("")}</select>
        </div>
        <div class="field">
          <label>Категория по умолчанию</label>
          <select id="quick-add-category">${CATEGORY_OPTIONS.map((c) => `<option value="${c}">${c}</option>`).join("")}</select>
        </div>
        <div class="field">
          <label>Группа в сайдбаре</label>
          <select id="quick-add-group">
            <option value="СМИ">СМИ</option>
            <option value="Регуляторы">Регуляторы</option>
            <option value="Telegram">Telegram</option>
          </select>
        </div>
        <div class="field">
          <label>Интервал опроса</label>
          <select id="quick-add-interval">${POLL_INTERVAL_OPTIONS.map((p) => `<option value="${p}">${p}</option>`).join("")}</select>
        </div>
      </div>

      <div class="quick-add__footer">
        <span class="quick-add__note">Источник будет автоматически проверен на доступность перед запуском</span>
        <button class="btn btn--primary" id="btn-quick-add-submit" type="button">Проверить и начать сбор →</button>
      </div>
    </div>
  `;
}

function sourceRowHtml(src) {
  const statusMeta = STATUS_META[src.status] || { pill: "" };
  const isActive = src.status === "Активен";
  return `
    <tr data-source-id="${src.id}">
      <td>${escapeHtml(src.name)}</td>
      <td>${escapeHtml(src.type)}</td>
      <td class="mono">${escapeHtml(src.url)}</td>
      <td><span class="status-pill ${statusMeta.pill}">${escapeHtml(src.status)}</span></td>
      <td class="mono">${escapeHtml(src.last_fetch)}</td>
      <td>
        <div style="display:flex; gap:2px;">
          <button class="icon-btn" data-action="toggle-source" title="${isActive ? "Поставить на паузу" : "Возобновить сбор"}">${isActive ? ICONS.pause : ICONS.play}</button>
          <button class="icon-btn" data-action="edit-source" title="Редактировать">${ICONS.edit}</button>
          <button class="icon-btn icon-btn--danger" data-action="delete-source" title="Удалить">${ICONS.trash}</button>
        </div>
      </td>
    </tr>
  `;
}

async function toggleSource(sourceId) {
  try {
    await Api.changeSource({ id: sourceId, action: "toggle" });
    await loadSources();
    if (state.view.type === "sources") renderSourcesView();
  } catch (err) {
    toast("Не удалось изменить статус источника: " + err.message, "error");
  }
}

async function deleteSource(sourceId) {
  try {
    await Api.removeSource(sourceId);
    delete state.newsCache[sourceId];
    await loadSources();
    if (state.view.type === "sources") renderSourcesView();
    toast("Источник удалён");
  } catch (err) {
    toast("Не удалось удалить источник: " + err.message, "error");
  }
}

async function submitQuickAddSource() {
  const url = document.getElementById("quick-add-url").value.trim();
  if (!url) { toast("Укажи URL или юзернейм канала", "error"); return; }

  const group = document.getElementById("quick-add-group").value;
  const type = document.getElementById("quick-add-type").value;
  const category = document.getElementById("quick-add-category").value;
  const interval = document.getElementById("quick-add-interval").value;

  const name = url.replace(/^https?:\/\//, "").split("/")[0];

  try {
    await Api.addSource({ name, url, group, type, category, poll_interval: interval });
    document.getElementById("quick-add-url").value = "";
    await loadSources();
    renderSourcesView();
    toast("Источник добавлен и проверен");
  } catch (err) {
    toast("Не удалось добавить источник: " + err.message, "error");
  }
}

function openNewsViewModal(n) {
  if (!n) return;

  const facts = [
    ["Кто", n.who], ["Что", n.what], ["Когда", n.when], ["Последствия", n.consequences],
  ].filter(([, v]) => v);

  $modalRoot.innerHTML = `
    <div class="modal-overlay">
      <div class="modal" data-news-id="${n.id}">
        <div class="modal__header">
          <h2 class="modal__title h-l">${n.object_type === "npa" ? "Цикл НПА" : "Просмотр публикации"}</h2>
          <button class="modal__close" data-action="close-modal">${ICONS.close}</button>
        </div>

        <div class="modal__section">
          <div class="card__badges" style="margin-bottom:8px;">
            ${n.category ? `<span class="badge" style="${categoryStyle(n.category)}">${escapeHtml(n.category)}</span>` : ""}
            ${n.importance ? `<span class="badge" style="${importanceStyle(n.importance)}">${escapeHtml(n.importance)}</span>` : ""}
            ${n.object_type === "npa" ? `<span class="badge">НПА</span>` : ""}
          </div>
          <h3 style="margin:0; font-size:18px; font-weight:600;">${escapeHtml(n.title || "Без заголовка")}</h3>
        </div>

        ${n.description ? `
        <div class="modal__section">
          <label>Аннотация</label>
          <p style="margin:4px 0 0; white-space:pre-wrap;">${escapeHtml(n.description)}</p>
        </div>` : ""}

        ${n.text ? `
        <div class="modal__section">
          <label>Текст новости</label>
          <div style="max-height:320px; overflow-y:auto; white-space:pre-wrap; padding:9px 12px; border:1px solid var(--border); border-radius:6px; background:var(--bg-muted, #f7f7f8); font-size:14px; line-height:1.5;">${escapeHtml(n.text)}</div>
        </div>` : ""}

        ${facts.length ? `
        <div class="modal__section">
          <dl class="card__facts" style="margin-bottom:0;">
            ${facts.map(([k, v]) => `<dt>${k}:</dt><dd>${escapeHtml(v)}</dd>`).join("")}
          </dl>
        </div>` : ""}

        ${n.lifecycle && n.lifecycle.length ? `
        <div class="modal__section">
          <div class="timeline-wrap__label">Жизненный цикл · ${n.lifecycle.length} стадий</div>
          ${lifecycleHtml(n.lifecycle)}
        </div>` : ""}

        ${n.tags && n.tags.length ? `
        <div class="modal__section card__tags">${n.tags.map((t) => `<span class="card__tag">${escapeHtml(t)}</span>`).join("")}</div>` : ""}

        <div class="modal__meta-row">
          <span>Источник: ${escapeHtml(n.source_name || "—")} · ${escapeHtml(n.pub_date || "")}</span>
          ${n.link ? `<a href="${escapeHtml(n.link)}" target="_blank" rel="noopener">Открыть оригинал →</a>` : ""}
        </div>

        <div class="modal__footer modal__footer--split">
          <span></span>
          <div style="display:flex; gap:8px;">
            <button class="btn btn--secondary" data-action="close-modal">Закрыть</button>
            <button class="btn btn--primary" data-action="edit-from-view">Редактировать</button>
          </div>
        </div>
      </div>
    </div>
  `;
}

document.addEventListener("DOMContentLoaded", init);