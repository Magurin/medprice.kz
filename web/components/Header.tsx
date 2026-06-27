"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useBasket } from "@/lib/basket";
import { useAuth } from "@/lib/auth";

import { SECTION_LINKS } from "@/lib/site-nav";

export default function Header() {
  const pathname = usePathname();
  const basket = useBasket();
  const { user, username, email, signOut, loading, isStaff } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // закрываем меню профиля по клику вне и при смене маршрута
  useEffect(() => {
    if (!menuOpen) return;
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [menuOpen]);

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);
  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);
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
            MedPrice<span className="text-brand">.kz</span>
          </span>
        </Link>

        <nav className="flex items-center gap-0.5 overflow-x-auto text-sm font-medium">
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

          {/* раздел для сотрудников — виден только staff (роль из public.staff) */}
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
                <div className="relative" ref={menuRef}>
                  <button
                    onClick={() => setMenuOpen((v) => !v)}
                    className="flex max-w-[140px] items-center gap-1 truncate rounded-lg px-2.5 py-2 text-foreground hover:bg-surface2"
                    title={email || undefined}
                    aria-haspopup="menu"
                    aria-expanded={menuOpen}
                  >
                    <span className="truncate">{who}</span>
                    <svg
                      className={`h-3.5 w-3.5 shrink-0 transition-transform ${menuOpen ? "rotate-180" : ""}`}
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.5"
                    >
                      <path d="M6 9l6 6 6-6" />
                    </svg>
                  </button>
                  {menuOpen && (
                    <div
                      role="menu"
                      className="absolute right-0 top-full mt-1.5 w-44 overflow-hidden rounded-xl border border-line bg-surface py-1 shadow-[0_18px_50px_-20px_rgba(12,24,34,0.35)]"
                    >
                      <Link
                        href="/subscriptions"
                        role="menuitem"
                        className="block px-3.5 py-2 text-foreground hover:bg-surface2"
                      >
                        Подписки
                      </Link>
                      <button
                        onClick={() => {
                          setMenuOpen(false);
                          signOut();
                        }}
                        role="menuitem"
                        className="block w-full px-3.5 py-2 text-left text-muted hover:bg-surface2 hover:text-foreground"
                      >
                        Выйти
                      </button>
                    </div>
                  )}
                </div>
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
      </div>
    </header>
  );
}
