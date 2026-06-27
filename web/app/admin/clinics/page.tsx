"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, CityRow, ClinicRow, cityLabel } from "@/lib/api";
import Rating from "@/components/Rating";
import CityPicker from "@/components/CityPicker";

export default function AdminClinicsPage() {
  const [cities, setCities] = useState<CityRow[]>([]);
  const [city, setCity] = useState("");
  const [q, setQ] = useState("");
  const [clinics, setClinics] = useState<ClinicRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.cities().then(setCities).catch(() => {});
  }, []);

  // в модерке показываем ВСЕ клиники (не только геокодированные)
  useEffect(() => {
    setLoading(true);
    api
      .clinics({ city: city || undefined, limit: 2000 })
      .then(setClinics)
      .catch(() => setClinics([]))
      .finally(() => setLoading(false));
  }, [city]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return clinics;
    return clinics.filter(
      (c) =>
        c.name.toLowerCase().includes(needle) ||
        (c.address ?? "").toLowerCase().includes(needle)
    );
  }, [clinics, q]);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Клиники</h2>
          <p className="text-sm text-muted">
            {loading ? "Загрузка…" : `${filtered.length} клиник${city ? ` · ${city}` : ""}`}
          </p>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        <CityPicker value={city} cities={cities} onChange={setCity} size="sm" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Поиск по названию или адресу…"
          className="min-w-[220px] flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm text-foreground placeholder:text-faint"
        />
      </div>

      <div className="overflow-hidden rounded-2xl border border-line bg-surface">
        {filtered.map((c) => (
          <Link
            key={c.id}
            href={`/admin/clinics/${c.id}`}
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
        {!loading && filtered.length === 0 && (
          <div className="px-4 py-10 text-center text-sm text-muted">
            {q.trim() ? "Ничего не нашлось по запросу." : "Нет клиник."}
          </div>
        )}
        {loading && (
          <div className="px-4 py-10 text-center text-sm text-muted">Загрузка…</div>
        )}
      </div>
    </div>
  );
}
