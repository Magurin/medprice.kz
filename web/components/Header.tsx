"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useBasket } from "@/lib/basket";
import { useAuth } from "@/lib/auth";

import { SECTION_LINKS, ADMIN_LINKS } from "@/lib/site-nav";

export default function Header() {
  const pathname = usePathname();
  const basket = useBasket();
  const { user, username, email, signOut, loading, isStaff } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  // закрываем мобильное меню при переходе на другую страницу
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  // активна только ссылка с самым длинным совпадающим префиксом —
  // иначе на /clinics/list подсветились бы и «Карта» (/clinics), и «Клиники».
  const bestMatch = SECTION_LINKS.reduce<string | null>((best, l) => {
    const ok = l.href === "/" ? pathname === "/" : pathname === l.href || pathname.startsWith(l.href + "/");
    if (!ok) return best;
    return best && best.length >= l.href.length ? best : l.href;
  }, null);
  const isActive = (href: string) => href === bestMatch;
  const who = username || email?.split("@")[0] || "аккаунт";

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface/85 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-full bg-brand text-white shadow-sm">
            <svg className="h-[22px] w-[22px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4">
              <path d="M12 3v18M3 12h18" />
            </svg>
          </span>
          <span className="text-[17px] font-semibold tracking-tight text-foreground">
            MedPrice<span className="text-brand">.xyz</span>
          </span>
        </Link>

        {/* десктоп-навигация */}
        <nav className="hidden items-center gap-0.5 text-sm font-medium lg:flex">
          {SECTION_LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 transition-colors ${
                isActive(l.href)
                  ? "text-brand-ink"
                  : "text-muted hover:bg-surface2 hover:text-foreground"
              }`}
            >
              {l.label}
              {l.href === "/compare" && basket.length > 0 && (
                <span className="grid h-5 min-w-5 place-items-center rounded-full bg-brand px-1 text-[11px] font-bold text-white">
                  {basket.length}
                </span>
              )}
            </Link>
          ))}

          {/* раздел для сотрудников - виден только staff (роль из public.staff) */}
          {isStaff && (
            <Link
              href="/admin"
              className={`flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 font-semibold transition-colors ${
                isActive("/admin")
                  ? "bg-brand/10 text-brand-ink"
                  : "text-brand hover:bg-brand/10"
              }`}
            >
              Модерация
            </Link>
          )}

          {/* блок авторизации */}
          {!loading && (
            <div className="ml-1 flex shrink-0 items-center gap-1.5 border-l border-line pl-2">
              {user ? (
                <>
                  <Link
                    href="/subscriptions"
                    className="max-w-[140px] truncate rounded-lg px-2.5 py-2 text-foreground hover:bg-surface2"
                    title={email || undefined}
                  >
                    {who}
                  </Link>
                  <button
                    onClick={() => signOut()}
                    className="rounded-lg px-2.5 py-2 text-muted hover:bg-surface2 hover:text-foreground"
                    title="Выйти"
                  >
                    Выйти
                  </button>
                </>
              ) : (
                <>
                  <Link href="/login" className="rounded-lg px-3 py-2 text-muted hover:bg-surface2 hover:text-foreground">
                    Войти
                  </Link>
                  <Link href="/register" className="rounded-lg bg-brand px-3 py-2 font-semibold text-white hover:bg-brand/90">
                    Регистрация
                  </Link>
                </>
              )}
            </div>
          )}
        </nav>

        {/* бургер — только на мобилке/планшете */}
        <button
          onClick={() => setMenuOpen((v) => !v)}
          aria-label={menuOpen ? "Закрыть меню" : "Открыть меню"}
          aria-expanded={menuOpen}
          className="relative grid h-10 w-10 place-items-center rounded-lg text-foreground hover:bg-surface2 lg:hidden"
        >
          <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            {menuOpen ? (
              <path d="M6 6l12 12M18 6 6 18" />
            ) : (
              <path d="M3 6h18M3 12h18M3 18h18" />
            )}
          </svg>
          {!menuOpen && basket.length > 0 && (
            <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-brand" />
          )}
        </button>
      </div>

      {/* мобильное меню */}
      {menuOpen && (
        <nav className="border-t border-line bg-surface px-4 py-3 text-sm font-medium lg:hidden">
          <div className="flex flex-col gap-0.5">
            {SECTION_LINKS.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className={`flex items-center justify-between rounded-lg px-3 py-2.5 transition-colors ${
                  isActive(l.href)
                    ? "bg-surface2 text-brand-ink"
                    : "text-muted hover:bg-surface2 hover:text-foreground"
                }`}
              >
                {l.label}
                {l.href === "/compare" && basket.length > 0 && (
                  <span className="grid h-5 min-w-5 place-items-center rounded-full bg-brand px-1 text-[11px] font-bold text-white">
                    {basket.length}
                  </span>
                )}
              </Link>
            ))}

            {isStaff && (
              <Link
                href="/admin"
                className={`rounded-lg px-3 py-2.5 font-semibold transition-colors ${
                  isActive("/admin") ? "bg-brand/10 text-brand-ink" : "text-brand hover:bg-brand/10"
                }`}
              >
                Модерация
              </Link>
            )}
          </div>

          {/* Подразделы модерации — только когда мы внутри панели (там нет своей навигации на мобилке) */}
          {isStaff && pathname.startsWith("/admin") && (
            <div className="mt-2 flex flex-col gap-0.5 border-t border-line pt-2">
              {ADMIN_LINKS.map((l) => {
                const active = l.href === "/admin" ? pathname === "/admin" : pathname.startsWith(l.href);
                return (
                  <Link
                    key={l.href}
                    href={l.href}
                    className={`rounded-lg px-3 py-2.5 transition-colors ${
                      active ? "bg-surface2 text-brand-ink" : "text-muted hover:bg-surface2 hover:text-foreground"
                    }`}
                  >
                    {l.label}
                  </Link>
                );
              })}
            </div>
          )}

          {!loading && (
            <div className="mt-2 flex flex-col gap-0.5 border-t border-line pt-2">
              {user ? (
                <>
                  <Link
                    href="/subscriptions"
                    className="truncate rounded-lg px-3 py-2.5 text-foreground hover:bg-surface2"
                  >
                    {who}
                  </Link>
                  <button
                    onClick={() => {
                      setMenuOpen(false);
                      signOut();
                    }}
                    className="rounded-lg px-3 py-2.5 text-left text-muted hover:bg-surface2 hover:text-foreground"
                  >
                    Выйти
                  </button>
                </>
              ) : (
                <div className="flex gap-2">
                  <Link
                    href="/login"
                    className="flex-1 rounded-lg border border-line px-3 py-2.5 text-center text-muted hover:bg-surface2"
                  >
                    Войти
                  </Link>
                  <Link
                    href="/register"
                    className="flex-1 rounded-lg bg-brand px-3 py-2.5 text-center font-semibold text-white hover:bg-brand/90"
                  >
                    Регистрация
                  </Link>
                </div>
              )}
            </div>
          )}
        </nav>
      )}
    </header>
  );
}
