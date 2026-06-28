import Link from "next/link";
import { LEGAL_LINKS, SECTION_LINKS } from "@/lib/site-nav";

const YEAR = new Date().getFullYear();

export default function Footer() {
  return (
    <footer className="relative bg-surface2">
      {/* soft organic divider instead of a hard hairline */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-line2 to-transparent" />
      <div className="mx-auto max-w-6xl px-4 py-14">
        <div className="grid gap-x-8 gap-y-10 md:grid-cols-12">
          {/* бренд */}
          <div className="md:col-span-5">
            <Link href="/" className="inline-flex items-center gap-2.5">
              <span className="grid h-8 w-8 place-items-center rounded-full bg-brand text-white shadow-sm">
                <svg className="h-[22px] w-[22px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4">
                  <path d="M12 3v18M3 12h18" />
                </svg>
              </span>
              <span className="text-[17px] font-semibold tracking-tight text-foreground">
                MedPrice<span className="text-brand">.xyz</span>
              </span>
            </Link>
            <p className="mt-4 max-w-xs text-sm leading-relaxed text-faint">
              Цены на медицинские услуги клиник Казахстана — в одном месте.
            </p>
          </div>

          {/* разделы */}
          <nav className="md:col-span-7" aria-label="Разделы сайта">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">Разделы</h2>
            <ul className="mt-4 grid grid-cols-2 gap-x-8 gap-y-3 text-sm sm:grid-cols-3">
              {SECTION_LINKS.map((l) => (
                <li key={l.href}>
                  <Link href={l.href} className="text-faint transition-colors hover:text-foreground">
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </div>

        {/* нижняя полоса: копирайт + дисклеймер слева, правовые ссылки справа */}
        <div className="mt-12 flex flex-col gap-4 border-t border-line pt-6 text-xs text-faint sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-2">
            <span>© {YEAR} MedPrice.xyz</span>
            <span className="hidden text-line2 sm:inline">·</span>
            <span>Цены носят справочный характер и не являются публичной офертой.</span>
          </div>
          <nav className="flex items-center gap-4" aria-label="Правовая информация">
            {LEGAL_LINKS.map((l) => (
              <Link key={l.href} href={l.href} className="transition-colors hover:text-foreground">
                {l.label}
              </Link>
            ))}
          </nav>
        </div>
      </div>
    </footer>
  );
}
