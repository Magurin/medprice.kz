import Link from "next/link";
import { LEGAL_LINKS, SECTION_LINKS } from "@/lib/site-nav";

const YEAR = new Date().getFullYear();

export default function Footer() {
  return (
    <footer className="border-t border-line bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-12">
        <div className="flex flex-col gap-10 md:flex-row md:items-start md:justify-between">
          <div className="max-w-xs">
            <Link href="/" className="text-base font-semibold text-foreground transition-colors hover:text-brand">
              MedPrice.kz
            </Link>
            <p className="mt-3 text-sm leading-relaxed text-faint">
              Цены на медуслуги клиник Казахстана - в одном месте.
            </p>
          </div>

          <nav className="grid grid-cols-2 gap-10 sm:gap-16">
            <div>
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">Разделы</h2>
              <ul className="mt-4 space-y-2.5 text-sm">
                {SECTION_LINKS.map((l) => (
                  <li key={l.href}>
                    <Link href={l.href} className="text-faint transition-colors hover:text-foreground">
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">Правовая информация</h2>
              <ul className="mt-4 space-y-2.5 text-sm">
                {LEGAL_LINKS.map((l) => (
                  <li key={l.href}>
                    <Link href={l.href} className="text-faint transition-colors hover:text-foreground">
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </nav>
        </div>

        <div className="mt-12 flex flex-col gap-2 border-t border-line pt-6 text-xs text-faint sm:flex-row sm:items-center sm:justify-between">
          <span>© {YEAR} MedPrice.kz</span>
          <span>Цены носят справочный характер и не являются публичной офертой.</span>
        </div>
      </div>
    </footer>
  );
}
