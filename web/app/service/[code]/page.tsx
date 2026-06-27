"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, CityRow, Compare, HistoryResponse, tenge, prettyClinic, cityLabel } from "@/lib/api";
import { PriceScale } from "@/components/PriceScale";
import PriceHistoryChart from "@/components/PriceHistoryChart";
import SubscribeButton from "@/components/SubscribeButton";
import AddToBasketButton from "@/components/AddToBasketButton";
import Rating from "@/components/Rating";
import SourceBadge from "@/components/SourceBadge";
import CityPicker from "@/components/CityPicker";

const PAGE = 25;

type SortMode = "relevant" | "cheap" | "expensive";

const SORTS: [SortMode, string][] = [
  ["relevant", "релевантные"],
  ["cheap", "дешевле"],
  ["expensive", "дороже"],
];

// Релевантность = рейтинг 2ГИС (больший вес) + дешевизна.
// У клиник без рейтинга берём нейтраль (~3.5/5), чтобы они не проваливались,
// пока оценки 2ГИС не подтянутся ко всем. Пример: 5.0@2000 релевантнее, чем 2.0@1500.
function relevance(price: number, rating: number | null | undefined, min: number, max: number) {
  const span = max - min || 1;
  const cheap = (max - price) / span; // 0..1, дешевле = выше
  const r = rating != null ? rating / 5 : 0.7; // 0..1
  return 0.65 * r + 0.35 * cheap;
}

export default function ServicePage() {
  const params = useParams<{ code: string }>();
  const code = decodeURIComponent(params.code);
  const sp = useSearchParams();

  const [city, setCity] = useState(sp.get("city") || "");
  const [cities, setCities] = useState<CityRow[]>([]);
  const [data, setData] = useState<Compare | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [limit, setLimit] = useState(PAGE);
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState<SortMode>("relevant");
  const [priceFrom, setPriceFrom] = useState("");
  const [priceTo, setPriceTo] = useState("");
  const [minRating, setMinRating] = useState(0);
  const [history, setHistory] = useState<HistoryResponse | null>(null);

  useEffect(() => {
    api.cities().then(setCities).catch(() => {});
  }, []);

  useEffect(() => {
    setHistory(null);
    api
      .history(code)
      .then((h) => setHistory(h.series.some((s) => s.points.length > 0) ? h : null))
      .catch(() => setHistory(null));
  }, [code]);

  useEffect(() => {
    setLoading(true);
    setErr(null);
    setLimit(PAGE);
    api
      .compare(code, city || undefined)
      .then((d) => setData(d))
      .catch((e) => {
        setErr(String(e));
        setData(null);
      })
      .finally(() => setLoading(false));
  }, [code, city]);

  const offers = useMemo(() => {
    if (!data) return [];
    const f = filter.trim().toLowerCase();
    const lo = priceFrom ? Number(priceFrom) : null;
    const hi = priceTo ? Number(priceTo) : null;
    return data.offers.filter((o) => {
      if (lo != null && o.price < lo) return false;
      if (hi != null && o.price > hi) return false;
      if (minRating > 0 && (o.rating ?? 0) < minRating) return false;
      if (f) {
        return (
          prettyClinic(o.clinic).toLowerCase().includes(f) ||
          (o.city || "").toLowerCase().includes(f) ||
          (o.address || "").toLowerCase().includes(f) ||
          o.raw_name.toLowerCase().includes(f)
        );
      }
      return true;
    });
  }, [data, filter, priceFrom, priceTo, minRating]);

  const sorted = useMemo(() => {
    if (!data) return offers;
    const { min, max } = data.stats;
    const list = [...offers];
    if (sort === "cheap") list.sort((a, b) => a.price - b.price);
    else if (sort === "expensive") list.sort((a, b) => b.price - a.price);
    else
      list.sort(
        (a, b) =>
          relevance(b.price, b.rating, min, max) - relevance(a.price, a.rating, min, max) ||
          (b.reviews_count ?? 0) - (a.reviews_count ?? 0) ||
          a.price - b.price
      );
    return list;
  }, [offers, sort, data]);

  return (
    <div className="mx-auto max-w-4xl px-4 py-7">
      <Link href="/search" className="inline-flex items-center gap-1 text-sm font-medium text-muted transition-colors hover:text-brand-ink">
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="m15 18-6-6 6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        к поиску
      </Link>

      {loading && (
        <div className="mt-5 space-y-4">
          <div className="h-8 w-2/3 animate-pulse rounded-lg bg-surface2" />
          <div className="h-40 animate-pulse rounded-2xl border border-line bg-surface2" />
          <div className="h-72 animate-pulse rounded-2xl border border-line bg-surface2" />
        </div>
      )}

      {err && !loading && (
        <div className="mt-5 rounded-2xl border border-line bg-warn-tint/60 p-5 text-warn">
          Нет данных по этой услуге{city ? ` в городе ${city}` : ""}. Попробуйте другой город.
        </div>
      )}

      {data && !loading && (
        <>
          <div className="mt-4 flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h1 className="text-2xl font-semibold tracking-tight text-foreground">{data.name}</h1>
              <div className="mt-1.5 flex flex-wrap items-center gap-2 text-sm text-muted">
                <span>{data.category}</span>
                {data.is_curated && (
                  <span className="rounded bg-brand-tint px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-brand-ink">
                    справочник
                  </span>
                )}
              </div>
            </div>
            <CityPicker value={city} cities={cities} onChange={setCity} size="sm" align="right" />
          </div>

          {/* SUMMARY */}
          <div className="mt-5 rounded-2xl border border-line bg-surface p-5 sm:p-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <div className="text-xs uppercase tracking-wide text-faint">дешевле всего</div>
                <div className="mt-0.5 text-3xl font-bold tabular-nums text-deal">{tenge(data.stats.min)}</div>
              </div>
              <div className="flex gap-6 text-right">
                <div>
                  <div className="text-xs text-faint">медиана</div>
                  <div className="text-base font-semibold tabular-nums text-foreground">{tenge(data.stats.median)}</div>
                </div>
                <div>
                  <div className="text-xs text-faint">дороже всего</div>
                  <div className="text-base font-semibold tabular-nums text-muted">{tenge(data.stats.max)}</div>
                </div>
              </div>
            </div>

            <div className="mt-5">
              <PriceScale min={data.stats.min} median={data.stats.median} max={data.stats.max} />
            </div>

            <div className="mt-5 rounded-xl bg-deal-tint/60 px-4 py-3 text-sm text-foreground">
              <span>
                <b>{data.stats.count}</b> клиник предлагают услугу. Между самой дешёвой и дорогой -{" "}
                <b className="tabular-nums">{tenge(data.stats.savings)}</b> разницы: можно сэкономить до{" "}
                <b className="text-deal">{data.stats.savings_pct}%</b>.
              </span>
            </div>

            <div className="mt-5 flex flex-wrap gap-2">
              <SubscribeButton code={data.code} city={city || undefined} />
              <AddToBasketButton code={data.code} name={data.name} />
            </div>

            {data.last_updated && (
              <div className="mt-4 flex items-center gap-1.5 text-xs text-faint">
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 7v5l3 2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                Цены актуальны на{" "}
                {new Date(data.last_updated).toLocaleDateString("ru-RU", {
                  day: "2-digit", month: "long", year: "numeric",
                })}
              </div>
            )}
          </div>

          {/* ИСТОРИЯ ЦЕН */}
          {history && (
            <div className="mt-5 rounded-2xl border border-line bg-surface p-5 sm:p-6">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-faint">
                  Динамика цены по годам
                </h2>
                <span className="text-xs text-faint">из архивных прайсов клиник</span>
              </div>
              <div className="mt-3">
                <PriceHistoryChart data={history} />
              </div>
            </div>
          )}

          {/* SORT + FILTER */}
          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-1 rounded-xl border border-line bg-surface p-1 text-xs font-medium">
              {SORTS.map(([key, label]) => (
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
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Фильтр по клинике…"
              className="h-9 w-40 rounded-lg border border-line2 bg-surface px-3 text-sm text-foreground outline-none transition-colors focus:border-brand sm:w-52"
            />
          </div>
          {sort === "relevant" && (
            <p className="mt-2 text-xs text-faint">
              Релевантность учитывает рейтинг 2ГИС и цену: выше - клиники с лучшей оценкой при разумной цене.
            </p>
          )}

          {/* ФИЛЬТРЫ: цена + рейтинг */}
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
            <div className="flex items-center gap-1.5">
              <span className="text-faint">Цена ₸:</span>
              <input
                value={priceFrom}
                onChange={(e) => setPriceFrom(e.target.value.replace(/\D/g, ""))}
                inputMode="numeric"
                placeholder="от"
                className="h-8 w-16 rounded-lg border border-line2 bg-surface px-2 text-foreground outline-none focus:border-brand"
              />
              <span className="text-faint">–</span>
              <input
                value={priceTo}
                onChange={(e) => setPriceTo(e.target.value.replace(/\D/g, ""))}
                inputMode="numeric"
                placeholder="до"
                className="h-8 w-16 rounded-lg border border-line2 bg-surface px-2 text-foreground outline-none focus:border-brand"
              />
            </div>
            <div className="flex items-center gap-1">
              <span className="mr-1 text-faint">Рейтинг:</span>
              {([[0, "любой"], [4, "4.0+"], [4.5, "4.5+"]] as [number, string][]).map(([v, label]) => (
                <button
                  key={v}
                  onClick={() => setMinRating(v)}
                  className={`rounded-lg px-2 py-1 font-medium transition-colors ${
                    minRating === v ? "bg-brand-tint text-brand-ink" : "text-muted hover:text-foreground"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            {(priceFrom || priceTo || minRating > 0) && (
              <button
                onClick={() => { setPriceFrom(""); setPriceTo(""); setMinRating(0); }}
                className="text-faint underline-offset-2 hover:text-foreground hover:underline"
              >
                сбросить
              </button>
            )}
            <span className="ml-auto text-faint">{sorted.length} из {data.stats.count}</span>
          </div>

          {/* LIST */}
          <div className="mt-3 overflow-hidden rounded-2xl border border-line bg-surface">
            {sorted.slice(0, limit).map((o, i) => {
              const top = i === 0 && !filter && sort !== "expensive";
              const cheapest = o.price === data.stats.min;
              return (
                <div
                  key={`${o.clinic}-${i}`}
                  className={`flex items-center gap-3 border-b border-line px-4 py-3 last:border-0 ${
                    top ? "bg-deal-tint/40" : "hover:bg-surface2"
                  }`}
                >
                  <span
                    className={`grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-bold tabular-nums ${
                      top ? "bg-deal text-white" : "bg-surface2 text-faint"
                    }`}
                  >
                    {i + 1}
                  </span>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      {o.clinic_id ? (
                        <Link
                          href={`/clinics/${o.clinic_id}`}
                          className="truncate font-medium text-foreground hover:text-brand-ink hover:underline"
                        >
                          {prettyClinic(o.clinic)}
                        </Link>
                      ) : o.source_url ? (
                        <a
                          href={o.source_url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="truncate font-medium text-foreground hover:text-brand-ink hover:underline"
                        >
                          {prettyClinic(o.clinic)}
                        </a>
                      ) : (
                        <span className="truncate font-medium text-foreground">{prettyClinic(o.clinic)}</span>
                      )}
                      {top && (
                        <span className="shrink-0 rounded-full bg-deal px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
                          {sort === "cheap" ? "лучшая цена" : "рекомендуем"}
                        </span>
                      )}
                      {o.rating != null && (
                        <span className="shrink-0">
                          <Rating rating={o.rating} count={o.reviews_count} url={o.twogis_url} size="xs" />
                        </span>
                      )}
                      <SourceBadge
                        sourceType={o.source_type}
                        sourceUrl={o.source_url}
                        sourceFile={o.source_file}
                        parsedAt={o.parsed_at}
                      />
                    </div>
                    {o.address && (
                      <div className="mt-0.5 truncate text-xs text-muted" title={o.address}>
                        {o.address}
                      </div>
                    )}
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-faint">
                      {!o.address && <><span className="shrink-0">{cityLabel(o.city)}</span><span className="text-line2">·</span></>}
                      {o.working_hours && (
                        <>
                          <span className="inline-flex shrink-0 items-center gap-1 text-faint">
                            <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <circle cx="12" cy="12" r="9" />
                              <path d="M12 7v5l3 2" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                            {o.working_hours}
                          </span>
                          <span className="text-line2">·</span>
                        </>
                      )}
                      <span className="truncate" title={o.raw_name}>{o.raw_name}</span>
                    </div>
                  </div>

                  <div className="shrink-0 whitespace-nowrap text-right">
                    <span className={`text-base font-bold tabular-nums ${cheapest ? "text-deal" : "text-foreground"}`}>
                      {o.is_from && <span className="mr-0.5 text-xs font-normal text-faint">от</span>}
                      {tenge(o.price)}
                    </span>
                  </div>
                </div>
              );
            })}

            {offers.length === 0 && (
              <div className="px-4 py-10 text-center text-sm text-muted">Ничего не нашлось по фильтру.</div>
            )}
          </div>

          {limit < offers.length && (
            <button
              onClick={() => setLimit((l) => l + PAGE * 2)}
              className="mt-3 w-full rounded-xl border border-line bg-surface py-3 text-sm font-medium text-brand-ink transition-colors hover:bg-surface2"
            >
              Показать ещё {Math.min(PAGE * 2, offers.length - limit)} из {offers.length}
            </button>
          )}

          <p className="mt-4 text-xs leading-relaxed text-faint">
            Серым под клиникой - оригинальное название услуги в её прайсе (до нормализации).
            «от» - цена указана как минимальная. Цены справочные, уточняйте в клинике.
          </p>
        </>
      )}
    </div>
  );
}
