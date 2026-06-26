import Link from "next/link";
import { LEGAL_LINKS, SECTION_LINKS } from "@/lib/site-nav";

const YEAR = new Date().getFullYear();

export default function Footer() {
  return (
    <footer className="border-t border-line bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-10">
        <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <Link href="/" className="font-medium text-muted transition-colors hover:text-foreground">
              MedPrice.kz
            </Link>
            <p className="mt-2 text-sm leading-relaxed text-faint">
              Агрегатор цен на медуслуги Казахстана. Цены собраны с публичных прайс-листов клиник,
              нормализованы и носят справочный характер — уточняйте в клинике.
            </p>
          </div>

          <div>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">Разделы</h2>
            <ul className="mt-3 space-y-2 text-sm">
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
            <ul className="mt-3 space-y-2 text-sm">
              {LEGAL_LINKS.map((l) => (
                <li key={l.href}>
                  <Link href={l.href} className="text-faint transition-colors hover:text-foreground">
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="mt-8 border-t border-line pt-6 text-xs text-faint">
          © {YEAR} MedPrice.kz. Информация на сайте не является медицинской консультацией или публичной офертой.
        </div>
      </div>
    </footer>
  );
}
