"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, CityRow, SearchResult, tenge } from "@/lib/api";
import CityPicker from "@/components/CityPicker";

export default function SearchBar({
  initialQuery = "",
  initialCity = "",
  big = false,
}: {
  initialQuery?: string;
  initialCity?: string;
  big?: boolean;
}) {
  const router = useRouter();
  const [q, setQ] = useState(initialQuery);
  const [city, setCity] = useState(initialCity);
  const [cities, setCities] = useState<CityRow[]>([]);
  const [sugg, setSugg] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.cities().then(setCities).catch(() => {});
  }, []);

  // живые подсказки с дебаунсом
  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) {
      setSugg([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const t = setTimeout(() => {
      api
        .search(term, city || undefined)
        .then((r) => setSugg(r.results.slice(0, 6)))
        .catch(() => setSugg([]))
        .finally(() => setLoading(false));
    }, 220);
    return () => clearTimeout(t);
  }, [q, city]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const goSearch = () => {
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (city) params.set("city", city);
    setOpen(false);
    router.push(`/search?${params.toString()}`);
  };

  const goService = (code: string) => {
    setOpen(false);
    router.push(`/service/${encodeURIComponent(code)}${city ? `?city=${encodeURIComponent(city)}` : ""}`);
  };

  // На мобилке поле поиска делаем выше и заметнее, а город с кнопкой — ниже и компактнее
  // (на одной строке). На sm+ всё выравнивается в единую панель одной высоты.
  const searchH = big ? "h-14 sm:h-[58px]" : "h-12";
  const ctlH = big ? "h-12 sm:h-[58px]" : "h-12";
  const text = big ? "text-base" : "text-sm";

  return (
    <div ref={boxRef} className="relative w-full">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          goSearch();
        }}
        className={`flex w-full flex-col gap-2 sm:flex-row sm:items-stretch sm:gap-0 sm:rounded-2xl sm:border sm:border-line2 sm:bg-surface sm:p-1.5 sm:shadow-[0_8px_30px_-12px_rgba(13,148,136,0.25)] ${text}`}
      >
        {/* поле услуги */}
        <div className={`relative flex w-full items-center rounded-xl border border-line2 bg-surface sm:w-auto sm:flex-1 sm:border-0 ${searchH}`}>
          <svg className="ml-3.5 h-5 w-5 shrink-0 text-faint" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.2-3.2" strokeLinecap="round" />
          </svg>
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            placeholder="Анализ, приём врача, МРТ, УЗИ…"
            className="h-full w-full bg-transparent px-3 text-foreground outline-none placeholder:text-faint"
          />
        </div>

        {/* город + кнопка: на мобилке одна компактная строка, на sm+ — части общей панели */}
        <div className="flex gap-2 sm:contents">
          {/* город */}
          <div className={`relative flex flex-1 items-center rounded-xl border border-line2 bg-surface sm:flex-none sm:border-0 sm:border-l sm:border-line sm:bg-transparent ${ctlH}`}>
            <CityPicker
              value={city}
              cities={cities}
              onChange={setCity}
              triggerClassName="flex h-full w-full min-w-0 cursor-pointer items-center gap-2 bg-transparent px-3.5 text-left outline-none sm:min-w-[150px] sm:px-3"
            />
          </div>

          <button
            type="submit"
            className={`shrink-0 rounded-xl bg-brand px-5 font-semibold text-white transition-colors hover:bg-brand-ink sm:px-7 ${ctlH}`}
          >
            Найти
          </button>
        </div>
      </form>

      {/* выпадающие подсказки */}
      {open && q.trim().length >= 2 && (
        <div className="absolute left-0 right-0 top-full z-40 mt-2 overflow-hidden rounded-2xl border border-line bg-surface shadow-[0_20px_50px_-20px_rgba(12,24,34,0.35)]">
          {loading && sugg.length === 0 && (
            <div className="px-4 py-3 text-sm text-faint">Ищем…</div>
          )}
          {!loading && sugg.length === 0 && (
            <div className="px-4 py-3 text-sm text-faint">Ничего не нашлось</div>
          )}
          {sugg.map((s) => (
            <button
              key={s.code}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => goService(s.code)}
              className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left transition-colors hover:bg-surface2"
            >
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-foreground">{s.name}</span>
                <span className="block truncate text-xs text-faint">
                  {s.category} · {s.clinics} клиник
                </span>
              </span>
              <span className="shrink-0 text-right text-sm font-semibold tabular-nums text-deal">
                от {tenge(s.min_price)}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
