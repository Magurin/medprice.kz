"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, CityRow, ClinicRow, cityLabel } from "@/lib/api";
import Rating from "@/components/Rating";
import CityPicker from "@/components/CityPicker";

const LIMIT = 500;

export default function ClinicsListPage() {
  const [cities, setCities] = useState<CityRow[]>([]);
  const [city, setCity] = useState("");
  const [q, setQ] = useState("");
  const [dq, setDq] = useState(""); // q с задержкой -> идёт в запрос
  const [clinics, setClinics] = useState<ClinicRow[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.cities().then(setCities).catch(() => {});
  }, []);

  // дебаунс поиска: клиник тысячи, фильтруем на сервере, а не в браузере
  useEffect(() => {
    const t = setTimeout(() => setDq(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    setLoading(true);
    setTotal(null);
    const p = { city: city || undefined, q: dq || undefined };
    api
      .clinics({ ...p, limit: LIMIT })
      .then(setClinics)
      .catch(() => setClinics([]))
      .finally(() => setLoading(false));
    api
      .clinicsCount(p)
      .then((r) => setTotal(r.count))
      .catch(() => setTotal(null));
  }, [city, dq]);

  const capped = clinics.length >= LIMIT;

  return (
    <div className="mx-auto max-w-3xl px-4 py-7">
      <div className="mb-4">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">Клиники</h1>
        <p className="mt-1 text-sm text-muted">
          {loading && total === null
            ? "Загрузка…"
            : `${(total ?? clinics.length).toLocaleString("ru-RU")} клиник${city ? ` · ${city}` : ""}`}
          {capped && total !== null && total > LIMIT && " · показаны первые 500, уточните поиск"}
        </p>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        <CityPicker value={city} cities={cities} onChange={setCity} size="sm" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Поиск по названию…"
          className="min-w-[220px] flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm text-foreground placeholder:text-faint outline-none transition-colors focus:border-brand"
        />
      </div>

      <div className="overflow-hidden rounded-2xl border border-line bg-surface">
        {clinics.map((c) => (
          <Link
            key={c.id}
            href={`/clinics/${c.id}`}
            className="flex items-center gap-3 border-b border-line px-4 py-3 last:border-0 transition-colors hover:bg-surface2"
          >
            <div className="min-w-0 flex-1">
              <div className="truncate font-medium text-foreground">{c.name}</div>
              <div className="truncate text-xs text-muted">
                {cityLabel(c.city)}
                {c.address ? ` · ${c.address}` : ""}
              </div>
            </div>
            {c.rating != null && (
              <Rating rating={c.rating} count={c.reviews_count} url={c.twogis_url} size="xs" />
            )}
            <svg className="h-4 w-4 shrink-0 text-faint" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="m9 18 6-6-6-6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Link>
        ))}
        {loading && <div className="px-4 py-10 text-center text-sm text-muted">Загрузка…</div>}
        {!loading && clinics.length === 0 && (
          <div className="px-4 py-10 text-center text-sm text-muted">
            {dq ? "Ничего не нашлось по запросу." : "Нет клиник."}
          </div>
        )}
      </div>
    </div>
  );
}
