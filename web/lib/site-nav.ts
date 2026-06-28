export const SECTION_LINKS = [
  { href: "/", label: "Поиск" },
  { href: "/search", label: "Каталог" },
  { href: "/clinics", label: "Карта" },
  { href: "/clinics/list", label: "Клиники" },
  { href: "/compare", label: "Сравнение" },
  { href: "/price-check", label: "Проверить прайс" },
] as const;

// Подразделы панели модерации. Используются и в layout админки (десктоп),
// и в бургер-меню хедера (мобилка) — поэтому живут здесь, в общем модуле.
export const ADMIN_LINKS = [
  { href: "/admin", label: "Обзор" },
  { href: "/admin/clinics", label: "Клиники" },
  { href: "/admin/import", label: "Импорт прайса" },
  { href: "/admin/parser", label: "Парсер" },
  { href: "/admin/sources", label: "Источники" },
  { href: "/admin/queue", label: "Очередь разметки" },
] as const;

export const LEGAL_LINKS = [
  { href: "/privacy", label: "Политика конфиденциальности" },
  { href: "/terms", label: "Пользовательское соглашение" },
] as const;
