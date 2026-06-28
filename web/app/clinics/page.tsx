"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, CityRow, ClinicRow } from "@/lib/api";
import ClinicsMap from "@/components/ClinicsMap";
import Rating from "@/components/Rating";
import CityPicker from "@/components/CityPicker";

export default function ClinicsPage() {
  const [cities, setCities] = useState<CityRow[]>([]);
  const [city, setCity] = useState("");
  const [q, setQ] = useState("");
  const [clinics, setClinics] = useState<ClinicRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  useEffect(() => {
    api.cities().then(setCities).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    api
      .clinics({ city: city || undefined, with_coords: true, limit: 500 })
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
    <div className="mx-auto max-w-6xl px-4 py-6">
      <div className="mb-4">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">Карта клиник</h1>
        <p className="mt-1 text-sm text-muted">
          {loading
            ? "Загрузка…"
            : `${filtered.length} клиник с координатами${city ? ` · ${city}` : " по Казахстану"}`}
        </p>
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

      <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
        <ul className="order-2 max-h-[420px] space-y-1 overflow-y-auto lg:order-1 lg:max-h-[600px]">
          {filtered.map((c) => (
            <li key={c.id}>
              <div
                className={`rounded-xl border px-3 py-2.5 transition-colors ${
                  c.id === selectedId
                    ? "border-brand/50 bg-surface2"
                    : "border-line bg-surface hover:bg-surface2"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <button onClick={() => setSelectedId(c.id)} className="min-w-0 flex-1 text-left font-medium leading-snug text-foreground">
                    {c.name}
                  </button>
                  <Rating rating={c.rating} count={c.reviews_count} url={c.twogis_url} size="xs" />
                </div>
                {c.address && <div className="mt-0.5 text-xs text-muted">{c.address}</div>}
                <Link
                  href={`/clinics/${c.id}`}
                  className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-brand-ink hover:underline"
                >
                  Услуги и контакты
                  <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="m9 18 6-6-6-6" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </Link>
              </div>
            </li>
          ))}
          {!loading && filtered.length === 0 && (
            <li className="rounded-xl border border-line bg-surface px-3 py-4 text-sm text-muted">
              Нет клиник с координатами. Запусти геокодинг (geocode.py), чтобы заполнить lat/lng.
            </li>
          )}
        </ul>

        <div className="relative isolate order-1 h-[420px] overflow-hidden rounded-2xl border border-line lg:order-2 lg:h-[600px]">
          <ClinicsMap clinics={filtered} selectedId={selectedId} onSelect={setSelectedId} />
        </div>
      </div>
    </div>
  );
}
