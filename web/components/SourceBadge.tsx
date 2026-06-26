"use client";

// Иконка-пометка источника данных. Наведение -> нативный тултип (title),
// который не обрезается родительским overflow-hidden, в отличие от absolute-блока.
//  • web  -> глобус (сайт клиники, парсинг); кликабелен -> источник
//  • file -> файл (архивный прайс), в тултипе имя файла

function fmtDate(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function host(url?: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

export default function SourceBadge({
  sourceType,
  sourceUrl,
  sourceFile,
  parsedAt,
}: {
  sourceType?: string | null;
  sourceUrl?: string | null;
  sourceFile?: string | null;
  parsedAt?: string | null;
}) {
  const isFile = sourceType === "file";
  const date = fmtDate(parsedAt);
  const site = host(sourceUrl);

  // текст нативного тултипа
  const lines = [
    "Источник",
    isFile ? "Архивный прайс клиники" : "Сайт клиники (парсинг)",
    isFile ? sourceFile : site,
    date ? `актуально на ${date}` : null,
  ].filter(Boolean);
  const tip = lines.join("\n");

  const Icon = isFile ? (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-[15px] w-[15px]">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" strokeLinejoin="round" />
      <path d="M14 3v5h5" strokeLinejoin="round" />
    </svg>
  ) : (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-[15px] w-[15px]">
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <ellipse cx="12" cy="12" rx="4" ry="9" />
    </svg>
  );

  const cls = "inline-flex shrink-0 items-center text-faint transition-colors hover:text-brand-ink";

  if (sourceUrl && !isFile) {
    return (
      <a href={sourceUrl} target="_blank" rel="noreferrer" title={tip} aria-label="Источник данных" onClick={(e) => e.stopPropagation()} className={cls}>
        {Icon}
      </a>
    );
  }
  return (
    <span title={tip} aria-label="Источник данных" className={cls}>
      {Icon}
    </span>
  );
}
