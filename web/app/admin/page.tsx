"use client";

import Link from "next/link";

// Обзор админки. Карточки — точки входа в инструменты модерации.
// Пока заглушка: сюда дальше ляжет статус парсера и счётчики очереди.
const TILES = [
  {
    href: "/admin/parser",
    title: "Модуль сбора данных",
    desc: "Запуск парсинга вручную, расписание (cron), журнал прогонов и ошибок по источникам.",
  },
  {
    href: "/admin/queue",
    title: "Очередь разметки",
    desc: "Строки прайсов, не привязанные к справочнику. Ручное сопоставление с канонической услугой.",
  },
];

export default function AdminHome() {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {TILES.map((t) => (
        <Link
          key={t.href}
          href={t.href}
          className="group rounded-2xl border border-line bg-surface p-5 transition-colors hover:border-brand"
        >
          <h2 className="text-base font-semibold text-foreground group-hover:text-brand-ink">{t.title}</h2>
          <p className="mt-1.5 text-sm text-muted">{t.desc}</p>
        </Link>
      ))}
    </div>
  );
}
