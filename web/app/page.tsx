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

const ic = "h-5 w-5";
const icFeat = "h-5 w-5";

const STEPS = [
  {
    n: "1",
    t: "Найдите услугу",
    d: "Введите анализ, приём врача или диагностику. Поиск понимает синонимы и сокращения - «ОАК» и «общий анализ крови» приведут к одной услуге.",
    icon: (
      <svg className={ic} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <circle cx="11" cy="11" r="7" />
        <path d="m21 21-4.3-4.3" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    n: "2",
    t: "Сравните клиники",
    d: "Цены десятков клиник в одном каталоге - от самой дешёвой к дорогой. Видно минимум, медиану и разброс, чтобы не переплатить.",
    icon: (
      <svg className={ic} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    n: "3",
    t: "Выберите выгодно",
    d: "Переходите на сайт клиники по прямой ссылке или соберите корзину из нескольких услуг и сравните итоговую стоимость.",
    icon: (
      <svg className={ic} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M20 6 9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
] as const;

const FEATURES = [
  {
    t: "Умный поиск названий",
    d: "Понимаем синонимы, сокращения и разные формулировки одной и той же услуги.",
    icon: (
      <svg className={icFeat} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M12 3v3M12 18v3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M3 12h3M18 12h3M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" strokeLinecap="round" />
        <circle cx="12" cy="12" r="3.2" />
      </svg>
    ),
  },
  {
    t: "Только публичные цены",
    d: "Собираем из открытых прайс-листов клиник - без рекламы, наценок и скрытых условий.",
    icon: (
      <svg className={icFeat} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M12 3 4 6v6c0 4.4 3.2 7.6 8 9 4.8-1.4 8-4.6 8-9V6l-8-3Z" strokeLinejoin="round" />
        <path d="m9 12 2 2 4-4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    t: "Прозрачное сравнение",
    d: "Минимум, медиана и максимум по каждой услуге - сразу видно справедливую цену.",
    icon: (
      <svg className={icFeat} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M3 3v18h18" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M7 14v3M12 9v8M17 5v12" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    t: "Данные всего Казахстана",
    d: "Клиники десятков городов, цены обновляются регулярно по публичным источникам.",
    icon: (
      <svg className={icFeat} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18M12 3c2.5 2.5 3.8 5.7 3.8 9s-1.3 6.5-3.8 9c-2.5-2.5-3.8-5.7-3.8-9S9.5 5.5 12 3Z" />
      </svg>
    ),
  },
] as const;

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
      <section className="relative overflow-x-clip border-b border-line">
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
        <section>
          <div className="mb-7 text-center">
            <h2 className="text-2xl font-semibold tracking-tight text-foreground">Как это работает</h2>
            <p className="mx-auto mt-2 max-w-xl text-pretty text-muted">
              Три шага от названия услуги до самой выгодной клиники - без звонков и обхода прайс-листов.
            </p>
          </div>

          <div className="relative grid gap-5 sm:grid-cols-3 sm:gap-6">
            {STEPS.map((s, i) => (
              <div
                key={s.n}
                className="group relative overflow-hidden rounded-2xl border border-line bg-surface p-6 transition-all hover:-translate-y-0.5 hover:border-brand/40 hover:shadow-[0_18px_36px_-22px_rgba(13,148,136,0.45)]"
              >
                <span
                  aria-hidden
                  className="pointer-events-none absolute -right-2 -top-4 select-none text-[88px] font-bold leading-none text-brand-tint/70"
                >
                  {s.n}
                </span>

                <span className="relative grid h-11 w-11 place-items-center rounded-xl bg-brand-tint text-brand-ink ring-1 ring-brand/15">
                  {s.icon}
                </span>

                <h3 className="relative mt-4 text-lg font-semibold text-foreground">{s.t}</h3>
                <p className="relative mt-1.5 text-sm leading-relaxed text-muted">{s.d}</p>

                {i < STEPS.length - 1 && (
                  <span className="absolute top-1/2 -right-3 z-10 hidden h-7 w-7 -translate-y-1/2 place-items-center rounded-full border border-line bg-surface text-brand shadow-sm sm:grid">
                    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                      <path d="m9 6 6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </span>
                )}
              </div>
            ))}
          </div>
        </section>

        {/* WHY US */}
        <section>
          <div className="mb-7 text-center">
            <h2 className="text-2xl font-semibold tracking-tight text-foreground">Почему MedPrice.kz</h2>
            <p className="mx-auto mt-2 max-w-xl text-pretty text-muted">
              Мы собираем цены за вас, приводим их к одному виду и показываем честно - без рекламы и наценок.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map((f) => (
              <div key={f.t} className="rounded-2xl border border-line bg-surface p-5">
                <span className="grid h-10 w-10 place-items-center rounded-lg bg-surface2 text-brand ring-1 ring-line">
                  {f.icon}
                </span>
                <h3 className="mt-3.5 font-semibold text-foreground">{f.t}</h3>
                <p className="mt-1 text-sm leading-relaxed text-muted">{f.d}</p>
              </div>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="relative overflow-hidden rounded-3xl border border-line bg-surface px-6 py-10 text-center sm:py-12">
          <div
            className="pointer-events-none absolute inset-0 -z-10"
            style={{
              background:
                "radial-gradient(70% 120% at 50% 0%, var(--brand-tint) 0%, transparent 65%)",
            }}
          />
          <h2 className="text-balance text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            Узнайте, сколько стоит ваша услуга
          </h2>
          <p className="mx-auto mt-2 max-w-lg text-pretty text-muted">
            Бесплатно, без регистрации. Введите название - и сравните цены клиник за пару секунд.
          </p>
          <Link
            href="/search"
            className="mt-6 inline-flex items-center gap-2 rounded-full bg-brand px-6 py-3 font-medium text-white shadow-sm transition-colors hover:bg-brand-ink"
          >
            Сравнить цены
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="m9 6 6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Link>
        </section>
      </div>
    </div>
  );
}
