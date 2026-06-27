"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, SearchResult, ServiceRow, tenge } from "@/lib/api";
import SearchBar from "@/components/SearchBar";
import { RangeBar } from "@/components/PriceScale";

type Sort = "cheapest" | "savings" | "clinics";

function ResultRow({ s, city }: { s: SearchResult; city: string }) {
  const savePct = s.max_price > s.min_price ? Math.round((1 - s.min_price / s.max_price) * 100) : 0;
  return (
    <Link
      href={`/service/${encodeURIComponent(s.code)}${city ? `?city=${encodeURIComponent(city)}` : ""}`}
      className="group flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4 transition-all hover:border-brand/40 hover:shadow-[0_14px_30px_-18px_rgba(13,148,136,0.5)] sm:flex-row sm:items-center sm:gap-5"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-medium text-foreground">{s.name}</span>
          {s.is_curated && (
            <span className="shrink-0 rounded bg-brand-tint px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-brand-ink">
              справочник
            </span>
          )}
        </div>
        <div className="mt-0.5 truncate text-xs text-faint">
          {s.category} · {s.clinics} клиник
        </div>
        <div className="mt-3 max-w-sm">
          <RangeBar min={s.min_price} max={s.max_price} avg={s.avg_price} />
        </div>
      </div>

      <div className="flex shrink-0 items-end justify-between gap-4 sm:flex-col sm:items-end sm:justify-center sm:text-right">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-faint">дешевле всего</div>
          <div className="text-lg font-bold tabular-nums text-deal">{tenge(s.min_price)}</div>
          <div className="text-xs tabular-nums text-faint">до {tenge(s.max_price)}</div>
        </div>
        {savePct >= 20 && (
          <span className="rounded-full bg-deal-tint px-2.5 py-1 text-xs font-semibold text-deal">
            экономия {savePct}%
          </span>
        )}
      </div>
    </Link>
  );
}

function Results() {
  const sp = useSearchParams();
  const q = sp.get("q") || "";
  const city = sp.get("city") || "";
  const category = sp.get("category") || "";

  const [loading, setLoading] = useState(true);
  const [priced, setPriced] = useState<SearchResult[]>([]);
  const [rows, setRows] = useState<ServiceRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>("cheapest");

  useEffect(() => {
    setLoading(true);
    setErr(null);
    const run = async () => {
      try {
        if (q) {
          const r = await api.search(q, city || undefined);
          setPriced(r.results);
          setRows([]);
        } else if (category) {
          const r = await api.services({ category, min_clinics: 2, limit: 120 });
          setRows(r);
          setPriced([]);
        } else {
          // каталог по умолчанию — весь перечень услуг, по популярности
          const r = await api.services({ min_clinics: 2, limit: 500 });
          setRows(r);
          setPriced([]);
        }
      } catch (e) {
        setErr(String(e));
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [q, city, category]);

  const sorted = [...priced].sort((a, b) => {
    if (sort === "cheapest") return a.min_price - b.min_price;
    if (sort === "clinics") return b.clinics - a.clinics;
    const sa = a.max_price > a.min_price ? 1 - a.min_price / a.max_price : 0;
    const sb = b.max_price > b.min_price ? 1 - b.min_price / b.max_price : 0;
    return sb - sa;
  });

  const categoryLabel = category === "Прочее" ? "Все услуги" : category;
  const title = q ? `«${q}»` : category ? categoryLabel : "Все услуги";

  return (
    <div className="mx-auto max-w-4xl px-4 py-7">
      <div className="mb-6">
        <SearchBar initialQuery={q} initialCity={city} />
      </div>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-2">
          <h1 className="text-xl font-semibold tracking-tight text-foreground">{title}</h1>
          {!loading && (priced.length > 0 || rows.length > 0) && (
            <span className="text-sm text-faint">{priced.length || rows.length} услуг</span>
          )}
        </div>
        {priced.length > 1 && (
          <div className="flex items-center gap-1 rounded-xl border border-line bg-surface p-1 text-xs font-medium">
            {([
              ["cheapest", "дешевле"],
              ["savings", "выгода"],
              ["clinics", "кол-во"],
            ] as [Sort, string][]).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setSort(key)}
                className={`rounded-lg px-2.5 py-1.5 transition-colors ${
                  sort === key ? "bg-brand-tint text-brand-ink" : "text-muted hover:text-foreground"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </div>

      {loading && (
        <div className="space-y-3">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-[104px] animate-pulse rounded-2xl border border-line bg-surface2" />
          ))}
        </div>
      )}
      {err && <div className="rounded-xl bg-warn-tint p-4 text-warn">Ошибка загрузки: {err}</div>}

      {!loading && !err && sorted.length === 0 && rows.length === 0 && (
        <div className="rounded-2xl border border-line bg-surface px-4 py-16 text-center">
          <div className="text-foreground">Ничего не нашлось</div>
          <div className="mt-1 text-sm text-muted">Попробуйте другое название услуги.</div>
        </div>
      )}

      {!loading && sorted.length > 0 && (
        <div className="space-y-3">
          {sorted.map((s) => (
            <ResultRow key={s.code} s={s} city={city} />
          ))}
        </div>
      )}

      {!loading && rows.length > 0 && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {rows.map((s) => (
            <Link
              key={s.code}
              href={`/service/${encodeURIComponent(s.code)}`}
              className="flex items-center justify-between gap-3 rounded-xl border border-line bg-surface px-4 py-3.5 transition-colors hover:border-brand/40 hover:bg-surface2"
            >
              <span className="min-w-0 truncate font-medium text-foreground">{s.name}</span>
              <span className="shrink-0 rounded-full bg-surface2 px-2.5 py-1 text-xs font-semibold text-muted">
                {s.clinics} клиник
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="py-16 text-center text-faint">Загрузка…</div>}>
      <Results />
    </Suspense>
  );
}
