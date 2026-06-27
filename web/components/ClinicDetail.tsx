"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, ClinicCard, tenge } from "@/lib/api";
import Rating from "@/components/Rating";

function host(url?: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

// Карточка клиники: контакты + услуги с ценами, сгруппированные по категории.
// Используется и в публичном разделе (/clinics/[id]), и в модерке (/admin/clinics/[id]).
export default function ClinicDetail({
  id,
  backHref,
  backLabel,
}: {
  id: number;
  backHref: string;
  backLabel: string;
}) {
  const [data, setData] = useState<ClinicCard | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    setLoading(true);
    setErr(null);
    api
      .clinicCard(id)
      .then(setData)
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [id]);

  // услуги, сгруппированные по категории (бэкенд уже отсортировал)
  const groups = useMemo(() => {
    if (!data) return [];
    const needle = q.trim().toLowerCase();
    const list = needle
      ? data.services.filter(
          (s) => s.service.toLowerCase().includes(needle) || s.raw_name.toLowerCase().includes(needle)
        )
      : data.services;
    const by = new Map<string, typeof list>();
    for (const s of list) {
      const cat = s.category || "Прочее";
      if (!by.has(cat)) by.set(cat, []);
      by.get(cat)!.push(s);
    }
    return [...by.entries()];
  }, [data, q]);

  return (
    <div>
      <Link
        href={backHref}
        className="inline-flex items-center gap-1 text-sm font-medium text-muted transition-colors hover:text-brand-ink"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="m15 18-6-6 6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {backLabel}
      </Link>

      {loading && (
        <div className="mt-5 space-y-4">
          <div className="h-8 w-2/3 animate-pulse rounded-lg bg-surface2" />
          <div className="h-32 animate-pulse rounded-2xl border border-line bg-surface2" />
          <div className="h-80 animate-pulse rounded-2xl border border-line bg-surface2" />
        </div>
      )}

      {err && !loading && (
        <div className="mt-5 rounded-2xl border border-line bg-warn-tint/60 p-5 text-warn">
          Клиника не найдена.
        </div>
      )}

      {data && !loading && (
        <>
          {/* ШАПКА: контакты */}
          <div className="mt-4 rounded-2xl border border-line bg-surface p-5 sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <h1 className="min-w-0 text-2xl font-semibold tracking-tight text-foreground">{data.name}</h1>
              {data.rating != null && (
                <Rating rating={data.rating} count={data.reviews_count} url={data.twogis_url} size="sm" />
              )}
            </div>

            <dl className="mt-4 space-y-2.5 text-sm">
              {data.address && (
                <div className="flex items-start gap-2.5">
                  <svg className="mt-0.5 h-4 w-4 shrink-0 text-faint" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
                    <circle cx="12" cy="10" r="3" />
                  </svg>
                  <span className="text-foreground">{data.address}</span>
                </div>
              )}
              {data.working_hours && (
                <div className="flex items-start gap-2.5">
                  <svg className="mt-0.5 h-4 w-4 shrink-0 text-faint" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="9" />
                    <path d="M12 7v5l3 2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span className="text-foreground">{data.working_hours}</span>
                </div>
              )}
              {data.phone && (
                <div className="flex items-start gap-2.5">
                  <svg className="mt-0.5 h-4 w-4 shrink-0 text-faint" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3-8.6A2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.2a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2Z" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <a href={`tel:${data.phone.replace(/\s/g, "")}`} className="text-foreground hover:text-brand-ink hover:underline">
                    {data.phone}
                  </a>
                </div>
              )}
              {data.source_url && data.source_type !== "file" && (
                <div className="flex items-start gap-2.5">
                  <svg className="mt-0.5 h-4 w-4 shrink-0 text-faint" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
                    <circle cx="12" cy="12" r="9" />
                    <path d="M3 12h18" />
                    <ellipse cx="12" cy="12" rx="4" ry="9" />
                  </svg>
                  <a href={data.source_url} target="_blank" rel="noreferrer" className="text-brand-ink hover:underline">
                    {host(data.source_url) || "сайт клиники"}
                  </a>
                </div>
              )}
            </dl>

            {data.lat != null && data.lng != null && (
              <div className="mt-4 flex flex-wrap gap-2">
                <a
                  href={`https://2gis.kz/geo/${data.lng},${data.lat}`}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-lg border border-line bg-surface px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-surface2"
                >
                  Показать на карте
                </a>
              </div>
            )}
          </div>

          {/* УСЛУГИ */}
          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold tracking-tight text-foreground">
              Услуги и цены <span className="text-sm font-normal text-faint">({data.services_count})</span>
            </h2>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Поиск услуги…"
              className="h-9 w-44 rounded-lg border border-line2 bg-surface px-3 text-sm text-foreground outline-none transition-colors focus:border-brand sm:w-56"
            />
          </div>

          <div className="mt-3 space-y-5">
            {groups.map(([cat, items]) => (
              <div key={cat}>
                <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-faint">{cat}</div>
                <div className="overflow-hidden rounded-2xl border border-line bg-surface">
                  {items.map((s) => (
                    <Link
                      key={s.code + s.raw_name}
                      href={`/service/${encodeURIComponent(s.code)}${data.city ? `?city=${encodeURIComponent(data.city)}` : ""}`}
                      className="flex items-center gap-3 border-b border-line px-4 py-3 last:border-0 hover:bg-surface2"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium text-foreground">{s.service}</div>
                        <div className="truncate text-xs text-faint" title={s.raw_name}>{s.raw_name}</div>
                      </div>
                      <span className="shrink-0 whitespace-nowrap text-base font-bold tabular-nums text-foreground">
                        {tenge(s.price)}
                      </span>
                    </Link>
                  ))}
                </div>
              </div>
            ))}
            {groups.length === 0 && (
              <div className="rounded-2xl border border-line bg-surface px-4 py-10 text-center text-sm text-muted">
                {q.trim()
                  ? "Ничего не нашлось по запросу."
                  : "Клиника не публикует цены онлайн — стоимость по запросу. Уточняйте в клинике."}
              </div>
            )}
          </div>

          <p className="mt-4 text-xs leading-relaxed text-faint">
            Серым - оригинальное название услуги в прайсе клиники. Цены справочные, уточняйте в клинике.
          </p>
        </>
      )}
    </div>
  );
}
