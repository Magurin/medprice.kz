import Link from "next/link";
import { api, SearchResult, tenge } from "@/lib/api";
import SearchBar from "@/components/SearchBar";
import { RangeBar } from "@/components/PriceScale";

// Прайсы меняются раз в сутки → страница статична с ежедневной ревалидацией
// (и точечной чисткой через /api/revalidate после фонового обновления данных).
export const revalidate = 86400;

const POPULAR_TAGS = [
  "Общий анализ крови",
  "Глюкоза",
  "ТТГ",
  "МРТ головного мозга",
  "УЗИ щитовидной железы",
  "ПСА",
];

const POPULAR_QUERIES = [
  "Общий анализ крови",
  "Глюкоза",
  "ТТГ",
  "Витамин D",
  "МРТ головного мозга",
  "УЗИ органов брюшной полости",
];

const nf = (n: number) => n.toLocaleString("ru-RU");

function TrustStrip({ items }: { items: { v: string; l: string }[] }) {
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-2 gap-y-1 text-sm text-muted">
      {items.map((it, i) => (
        <span key={it.l} className="flex items-center gap-2">
          {i > 0 && <span className="text-line2">·</span>}
          <span>
            <b className="font-semibold tabular-nums text-foreground">{it.v}</b> {it.l}
          </span>
        </span>
      ))}
    </div>
  );
}

function PopularCard({ s }: { s: SearchResult }) {
  const savePct = s.max_price > s.min_price ? Math.round((1 - s.min_price / s.max_price) * 100) : 0;
  return (
    <Link
      href={`/service/${encodeURIComponent(s.code)}`}
      className="group flex flex-col justify-between rounded-2xl border border-line bg-surface p-4 transition-all hover:-translate-y-0.5 hover:border-brand/40 hover:shadow-[0_14px_30px_-18px_rgba(13,148,136,0.5)]"
    >
      <div className="flex items-start justify-between gap-2">
        <span className="font-medium leading-snug text-foreground">{s.name}</span>
        {savePct >= 30 && (
          <span className="shrink-0 rounded-full bg-deal-tint px-2 py-0.5 text-xs font-semibold text-deal">
            −{savePct}%
          </span>
        )}
      </div>
      <div className="mt-4">
        <RangeBar min={s.min_price} max={s.max_price} avg={s.avg_price} />
        <div className="mt-2.5 flex items-baseline justify-between">
          <span className="text-sm text-faint">
            от <span className="font-semibold tabular-nums text-deal">{tenge(s.min_price)}</span>
          </span>
          <span className="text-xs text-faint">{s.clinics} клиник</span>
        </div>
      </div>
    </Link>
  );
}

export default async function Home() {
  const [stats, categories, popularRaw] = await Promise.all([
    api.stats().catch(() => null),
    api.categories().catch(() => []),
    Promise.all(
      POPULAR_QUERIES.map((term) =>
        api
          .search(term)
          .then((r) => r.results[0])
          .catch(() => undefined)
      )
    ),
  ]);
  const popular = popularRaw.filter((s): s is SearchResult => !!s);

  return (
    <div>
      {/* HERO */}
      <section className="relative overflow-hidden border-b border-line">
        <div
          className="pointer-events-none absolute inset-0 -z-10"
          style={{
            background:
              "radial-gradient(60% 80% at 50% -10%, var(--brand-tint) 0%, transparent 60%), linear-gradient(to bottom, #fbfdfd, var(--background))",
          }}
        />
        <div className="mx-auto max-w-3xl px-4 pb-12 pt-14 text-center sm:pb-16 sm:pt-20">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-muted shadow-sm">
            <span className="h-1.5 w-1.5 rounded-full bg-deal" />
            Цены клиник всего Казахстана в одном месте
          </span>

          <h1 className="mt-5 text-balance text-3xl font-semibold leading-[1.1] tracking-tight text-foreground sm:text-[44px]">
            Один анализ. Десятки клиник.
            <br />
            <span className="text-brand">Одна честная цена.</span>
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-pretty text-muted sm:text-lg">
            Сравните стоимость анализов, приёмов врачей, диагностики между клиниками - и
            выберите самое выгодное предложение. Вы достойны лучшего.
          </p>

          <div className="mx-auto mt-8 max-w-2xl">
            <SearchBar big />
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-sm">
            <span className="text-faint">Часто ищут:</span>
            {POPULAR_TAGS.map((p) => (
              <Link
                key={p}
                href={`/search?q=${encodeURIComponent(p)}`}
                className="rounded-full border border-line bg-surface px-3 py-1 text-muted transition-colors hover:border-brand/40 hover:text-brand-ink"
              >
                {p}
              </Link>
            ))}
          </div>

          {stats && (
            <div className="mt-8">
              <TrustStrip
                items={[
                  { v: nf(stats.clinics), l: "клиник" },
                  { v: nf(stats.cities), l: "городов" },
                  { v: nf(stats.comparable_services), l: "сравнимых услуг" },
                  { v: nf(stats.priced_offers), l: "цен в базе" },
                ]}
              />
            </div>
          )}
        </div>
      </section>

      <div className="mx-auto max-w-6xl space-y-14 px-4 py-14">
        {/* POPULAR COMPARISONS */}
        {popular.length > 0 && (
          <section>
            <div className="mb-5 flex items-end justify-between">
              <div>
                <h2 className="text-xl font-semibold tracking-tight text-foreground">
                  Популярные сравнения
                </h2>
                <p className="mt-1 text-sm text-muted">Где одна и та же услуга стоит дешевле всего</p>
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {popular.map((s) => (
                <PopularCard key={s.code} s={s} />
              ))}
            </div>
          </section>
        )}

        {/* CATEGORIES */}
        {categories.length > 0 && (
          <section>
            <h2 className="mb-5 text-xl font-semibold tracking-tight text-foreground">
              По категориям
            </h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {categories.slice(0, 12).map((c) => (
                <Link
                  key={c.category}
                  href={`/search?category=${encodeURIComponent(c.category)}`}
                  className="group flex items-center justify-between rounded-xl border border-line bg-surface px-4 py-3.5 transition-colors hover:border-brand/40 hover:bg-surface2"
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-foreground">{c.category}</span>
                    <span className="text-xs text-faint">{c.services} услуг</span>
                  </span>
                  <svg className="h-4 w-4 shrink-0 text-line2 transition-colors group-hover:text-brand" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="m9 6 6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </Link>
              ))}
            </div>
          </section>
        )}

        {/* HOW IT WORKS */}
        <section className="grid gap-3 sm:grid-cols-3">
          {[
            { n: "1", t: "Найдите услугу", d: "Введите анализ, приём или диагностику — мы поймём разные названия одной услуги." },
            { n: "2", t: "Сравните клиники", d: "Цены десятков клиник в одной таблице — от самой дешёвой к дорогой." },
            { n: "3", t: "Выберите выгодно", d: "Видите разброс и медиану — и переходите на сайт клиники по ссылке." },
          ].map((s) => (
            <div key={s.n} className="rounded-2xl border border-line bg-surface p-5">
              <span className="grid h-8 w-8 place-items-center rounded-full bg-brand-tint text-sm font-bold text-brand-ink">
                {s.n}
              </span>
              <h3 className="mt-3 font-semibold text-foreground">{s.t}</h3>
              <p className="mt-1 text-sm leading-relaxed text-muted">{s.d}</p>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
