const API_BASE = "http://localhost:8000";
 
const CATEGORY_META = {
  "Политика":      { bg: "var(--cat-politics-bg)",   fg: "var(--cat-politics-fg)" },
  "Экономика":     { bg: "var(--cat-economy-bg)",    fg: "var(--cat-economy-fg)" },
  "Технологии":    { bg: "var(--cat-tech-bg)",        fg: "var(--cat-tech-fg)" },
  "Регулирование": { bg: "var(--cat-regulation-bg)",  fg: "var(--cat-regulation-fg)" },
  "Общество":      { bg: "var(--cat-society-bg)",     fg: "var(--cat-society-fg)" },
};
 
const IMPORTANCE_META = {
  "Высокий": { bg: "var(--imp-high-bg)",   fg: "var(--imp-high-fg)" },
  "Средний": { bg: "var(--imp-medium-bg)", fg: "var(--imp-medium-fg)" },
  "Низкий":  { bg: "var(--imp-low-bg)",    fg: "var(--imp-low-fg)" },
};
 
const STATUS_META = {
  "Активен": { pill: "status-pill--active", dot: "status-dot--active" },
  "Пауза":   { pill: "status-pill--paused", dot: "status-dot--paused" },
  "Ошибка":  { pill: "status-pill--error",  dot: "status-dot--error" },
};
 
const CATEGORY_OPTIONS = Object.keys(CATEGORY_META);
const IMPORTANCE_OPTIONS = Object.keys(IMPORTANCE_META);
const SOURCE_TYPE_OPTIONS = ["СМИ", "Регулятор", "Telegram"];
const POLL_INTERVAL_OPTIONS = ["Каждые 15 минут", "Каждые 30 минут", "Каждый час", "Каждые 6 часов"];
 
function categoryStyle(name) {
  const m = CATEGORY_META[name] || { bg: "#F3F4F6", fg: "#6B7280" };
  return `background:${m.bg}; color:${m.fg};`;
}
 
function importanceStyle(name) {
  const m = IMPORTANCE_META[name] || { bg: "#F3F4F6", fg: "#6B7280" };
  return `background:${m.bg}; color:${m.fg};`;
}