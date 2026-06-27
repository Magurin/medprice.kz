"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useBasket } from "@/lib/basket";
import { useAuth } from "@/lib/auth";

import { SECTION_LINKS } from "@/lib/site-nav";

export default function Header() {
  const pathname = usePathname();
  const basket = useBasket();
  const { user, username, email, signOut, loading, isStaff } = useAuth();
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
      </div>
    </header>
  );
}
