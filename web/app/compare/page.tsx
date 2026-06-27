"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  api,
  BasketResponse,
  CityRow,
  ServiceRow,
  tenge,
  prettyClinic,
  twoGisRoute,
} from "@/lib/api";
import { useBasket, addToBasket, removeFromBasket, clearBasket } from "@/lib/basket";
import CityPicker from "@/components/CityPicker";
import Rating from "@/components/Rating";

// Поиск услуг для добавления в корзину.
function ServicePicker() {
  const items = useBasket();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<ServiceRow[]>([]);

  useEffect(() => {
    const t = setTimeout(() => {
      if (q.trim().length < 2) {
        setResults([]);
        return;
      }
      api.services({ q, limit: 8 }).then(setResults).catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <div className="relative">
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Добавить услугу в сравнение…"
        className="w-full rounded-xl border border-line2 bg-surface px-3.5 py-2.5 text-sm text-foreground outline-none focus:border-brand"
      />
      {results.length > 0 && (
        <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-xl border border-line bg-surface shadow-lg">
          {results.map((s) => {
            const added = items.some((i) => i.code === s.code);
            return (
              <button
                key={s.code}
                onClick={() => {
                  if (!added) addToBasket({ code: s.code, name: s.name });
                  setQ("");
                  setResults([]);
                }}
                className="flex w-full items-center justify-between gap-2 px-3.5 py-2.5 text-left text-sm hover:bg-surface2"
              >
                <span className="truncate text-foreground">{s.name}</span>
                <span className="shrink-0 text-xs text-faint">{added ? "уже в корзине" : "+ добавить"}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function ComparePage() {
  const basket = useBasket();
  const [cities, setCities] = useState<CityRow[]>([]);
  const [city, setCity] = useState("");
  const [data, setData] = useState<BasketResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.cities().then(setCities).catch(() => {});
  }, []);

  const codes = useMemo(() => basket.map((b) => b.code).join(","), [basket]);

  useEffect(() => {
    if (basket.length === 0) {
      setData(null);
      return;
    }
    setLoading(true);
    api
      .compareBasket(basket.map((b) => b.code), city || undefined)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codes, city]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-7">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">Сравнение клиник</h1>
          <p className="mt-1 text-sm text-muted">
            Соберите корзину услуг - покажем цены по клиникам и самую выгодную.
          </p>
        </div>
        {basket.length > 0 && (
          <button onClick={clearBasket} className="text-sm text-muted hover:text-warn">
            Очистить корзину
          </button>
        )}
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-[1fr_220px]">
        <ServicePicker />
        <CityPicker value={city} cities={cities} onChange={setCity} />
      </div>

      {/* чипы корзины */}
      {basket.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {basket.map((b) => (
            <span
              key={b.code}
              className="inline-flex items-center gap-1.5 rounded-full border border-line2 bg-surface2 px-3 py-1 text-sm text-foreground"
            >
              {b.name}
              <button onClick={() => removeFromBasket(b.code)} className="text-faint hover:text-warn">
                ✕
              </button>
            </span>
          ))}
        </div>
      )}

      {basket.length === 0 && (
        <div className="mt-8 rounded-2xl border border-dashed border-line2 bg-surface p-10 text-center">
          <p className="text-muted">Корзина пуста.</p>
          <p className="mt-1 text-sm text-faint">
            Найдите услуги через поиск выше или кнопку «В сравнение» на странице услуги.
          </p>
          <Link href="/search" className="mt-4 inline-block rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white">
            Перейти в каталог
          </Link>
        </div>
      )}

      {loading && <div className="mt-6 h-64 animate-pulse rounded-2xl border border-line bg-surface2" />}

      {data && !loading && data.clinics.length > 0 && (
        <div className="mt-6 overflow-x-auto rounded-2xl border border-line">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-surface2 text-left">
                <th className="sticky left-0 z-10 bg-surface2 px-4 py-3 font-semibold text-foreground">Клиника</th>
                {data.services.map((s) => (
                  <th key={s.code} className="min-w-[120px] px-3 py-3 font-medium text-muted">
                    {s.name}
                  </th>
                ))}
                <th className="px-4 py-3 text-right font-semibold text-foreground">Итого</th>
                <th className="px-3 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {data.clinics.map((c) => {
                const best = c.clinic_id === data.cheapest_complete;
                const route = twoGisRoute(c.lat, c.lng);
                return (
                  <tr
                    key={c.clinic_id}
                    className={`border-t border-line ${best ? "bg-deal-tint/40" : "hover:bg-surface2/50"}`}
                  >
                    <td className="sticky left-0 z-10 bg-inherit px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-foreground">{prettyClinic(c.clinic)}</span>
                        {best && (
                          <span className="rounded-full bg-deal px-2 py-0.5 text-[10px] font-bold uppercase text-white">
                            выгодно
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-xs text-faint">
                        <span>{c.city || "город не указан"}</span>
                        <Rating rating={c.rating} count={c.reviews_count} url={c.twogis_url} size="xs" />
                      </div>
                    </td>
                    {data.services.map((s) => {
                      const p = c.prices[s.code];
                      return (
                        <td key={s.code} className="px-3 py-3 tabular-nums">
                          {p != null ? (
                            tenge(p)
                          ) : (
                            <span className="text-faint" title="Нет в этой клинике">-</span>
                          )}
                        </td>
                      );
                    })}
                    <td className="px-4 py-3 text-right">
                      <span className={`font-bold tabular-nums ${best ? "text-deal" : "text-foreground"}`}>
                        {tenge(c.total)}
                      </span>
                      {!c.is_complete && (
                        <div className="text-[11px] text-faint">{c.covered}/{data.services.length} услуг</div>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      {route && (
                        <a
                          href={route}
                          target="_blank"
                          rel="noreferrer"
                          className="whitespace-nowrap rounded-lg border border-line2 px-2.5 py-1.5 text-xs font-medium text-brand-ink hover:bg-surface2"
                        >
                          🚗 2ГИС
                        </a>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {data && !loading && data.clinics.length === 0 && (
        <div className="mt-6 rounded-2xl border border-line bg-warn-tint/40 p-6 text-sm text-warn">
          Нет клиник с ценами по выбранным услугам{city ? ` в городе ${city}` : ""}.
        </div>
      )}

      {data && data.clinics.length > 0 && (
        <p className="mt-4 text-xs leading-relaxed text-faint">
          «Итого» - сумма минимальных цен по клинике для услуг корзины. Клиники с полным покрытием
          показаны выше; «-» означает, что услуги нет в прайсе клиники. Цены справочные.
        </p>
      )}
    </div>
  );
}
