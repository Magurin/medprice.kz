"use client";

import Link from "next/link";
import { ReactNode } from "react";

// Полноэкранный layout для auth-страниц: светлый прохладный фон, по центру белая
// карточка с мягкой тенью (контраст «белое на светло-сером»), лого сверху, футер снизу.
export default function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-[#eef2f7]">
      <main className="flex flex-1 items-center justify-center px-4 py-10 sm:py-14">
        <div className="w-full max-w-md">
          {/* лого над карточкой */}
          <Link href="/" className="mx-auto flex w-fit items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-full bg-brand text-white shadow-sm">
              <svg className="h-[22px] w-[22px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4">
                <path d="M12 3v18M3 12h18" />
              </svg>
            </span>
            <span className="text-lg font-semibold tracking-tight text-foreground">
              MedPrice<span className="text-brand">.kz</span>
            </span>
          </Link>

          {/* карточка */}
          <div className="mt-7 rounded-3xl border border-line bg-surface p-6 shadow-[0_18px_50px_-20px_rgba(12,24,34,0.25)] sm:mt-8 sm:p-8">
            <h1 className="text-center text-xl font-bold tracking-tight text-foreground sm:text-2xl">{title}</h1>
            {subtitle && <p className="mt-1.5 text-center text-sm text-muted">{subtitle}</p>}
            <div className="mt-6">{children}</div>
          </div>
        </div>
      </main>

      <footer className="px-5 py-5">
        <div className="mx-auto flex max-w-md items-center justify-between text-xs text-faint">
          <span>© 2026 MedPrice.kz</span>
          <Link href="/" className="transition-colors hover:text-muted">
            На сайт
          </Link>
        </div>
      </footer>
    </div>
  );
}
