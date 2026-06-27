"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";

// Клиентский гейт: вход в админку только для staff.
// Это «забор» UI — реальную защиту данных делает бэкенд (verify_staff на ручках),
// потому что FastAPI ходит в БД мимо RLS. Здесь просто не пускаем и прячем.
const ADMIN_LINKS = [
  { href: "/admin", label: "Обзор" },
  { href: "/admin/parser", label: "Парсер" },
  { href: "/admin/sources", label: "Источники" },
  { href: "/admin/queue", label: "Очередь разметки" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { loading, isStaff, role, email } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !isStaff) router.replace("/");
  }, [loading, isStaff, router]);

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-20 text-center text-muted">Проверяем доступ…</div>
    );
  }
  if (!isStaff) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-20 text-center text-muted">
        Раздел только для сотрудников. Перенаправляем…
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
        <div>
          <h1 className="text-lg font-semibold text-foreground">Панель модерации</h1>
          <p className="text-sm text-muted">
            {email} · роль: <span className="font-medium text-brand-ink">{role}</span>
          </p>
        </div>
        <nav className="flex items-center gap-1 text-sm font-medium">
          {ADMIN_LINKS.map((l) => {
            const active = l.href === "/admin" ? pathname === "/admin" : pathname.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`rounded-lg px-3 py-2 transition-colors ${
                  active ? "bg-surface2 text-brand-ink" : "text-muted hover:bg-surface2 hover:text-foreground"
                }`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
      </div>
      {children}
    </div>
  );
}
