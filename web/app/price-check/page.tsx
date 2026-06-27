"use client";

import { useEffect, useState } from "react";
import { api, CityRow, MatchResult, tenge } from "@/lib/api";
import CityPicker from "@/components/CityPicker";

const SAMPLE = `Клинический анализ крови (с лейкоцитарной формулой); 2500
ТТГ ультрачувствительный; 1500
МРТ артерий и вен головного мозга; 40000
УЗИ щитовидной железы; 9000`;

// Разбор строки прайса: поддерживаем «название; цена», «название<tab>цена»
// и просто «название 9000» (цена в конце строки) - чтобы можно было вставить
// прайс почти в любом виде.
function parseLine(l: string): { name: string; price?: number } {
  const sep = Math.max(l.lastIndexOf(";"), l.lastIndexOf("\t"));
  if (sep !== -1) {
    const price = parseInt(l.slice(sep + 1).replace(/\D/g, ""), 10);
    return { name: l.slice(0, sep).trim(), price: Number.isNaN(price) ? undefined : price };
  }
  const m = l.match(/^(.+?)[\s ]+(\d[\d\s ]*)(?:₸|тг|тенге)?$/i);
  if (m) {
    const price = parseInt(m[2].replace(/\D/g, ""), 10);
    return { name: m[1].trim(), price: Number.isNaN(price) ? undefined : price };
  }
  return { name: l };
}

function VerdictPill({ v }: { v?: string }) {
  if (!v) return <span className="text-faint">-</span>;
  const expensive = v === "дороже рынка";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${
        expensive ? "bg-warn-tint text-warn" : "bg-deal-tint text-deal"
      }`}
    >
      {v}
    </span>
  );
}

export default function PriceCheckPage() {
  const [text, setText] = useState(SAMPLE);
  const [city, setCity] = useState("");
  const [cities, setCities] = useState<CityRow[]>([]);
  const [results, setResults] = useState<MatchResult[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.cities().then(setCities).catch(() => {});
  }, []);

  const run = async () => {
    const items = text
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map(parseLine);
    setLoading(true);
    try {
      const r = await api.matchPrices(items, city || undefined);
      setResults(r.results);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-muted">
        <span className="h-1.5 w-1.5 rounded-full bg-brand" />
        для клиник и пациентов
      </span>
      <h1 className="mt-3 text-2xl font-semibold tracking-tight text-foreground">
        Завышена ли цена? Сравните прайс с рынком
      </h1>
      <p className="mt-2 max-w-2xl text-muted">
        Вставьте список услуг с ценами - из счёта клиники или своего прайс-листа. Мы
        распознаем каждую услугу, найдём её цену в других клиниках и покажем, где вы платите
        дороже рынка, а где выгоднее.
      </p>

      {/* для кого */}
      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        <div className="flex gap-3 rounded-2xl border border-line bg-surface p-4">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-tint text-brand-ink">
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M20 12v-1a8 8 0 1 0-8 8h1" strokeLinecap="round" />
              <path d="M16 16.5 18 18l3.5-3.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <div>
            <h3 className="font-semibold text-foreground">Пациенту</h3>
            <p className="mt-0.5 text-sm leading-relaxed text-muted">
              Получили счёт или прайс в клинике? Проверьте до оплаты, не дороже ли это, чем в
              среднем по рынку.
            </p>
          </div>
        </div>
        <div className="flex gap-3 rounded-2xl border border-line bg-surface p-4">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-tint text-brand-ink">
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M3 3v18h18" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M7 14v3M12 9v8M17 5v12" strokeLinecap="round" />
            </svg>
          </span>
          <div>
            <h3 className="font-semibold text-foreground">Клинике</h3>
            <p className="mt-0.5 text-sm leading-relaxed text-muted">
              Сравните свой прайс с конкурентами: где цены выше рынка, а где вы выгоднее
              остальных.
            </p>
          </div>
        </div>
      </div>

      {/* ввод прайса */}
      <div className="mt-6 rounded-2xl border border-line bg-surface p-4 sm:p-5">
        <div className="mb-2 flex items-center justify-between gap-3">
          <label className="text-sm font-medium text-foreground">
            Ваш прайс{" "}
            <span className="font-normal text-faint">- по одной услуге в строке</span>
          </label>
          <button
            type="button"
            onClick={() => setText(SAMPLE)}
            className="shrink-0 text-xs font-medium text-brand transition-colors hover:text-brand-ink"
          >
            Вставить пример
          </button>
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          spellCheck={false}
          placeholder={"Клинический анализ крови; 2500\nУЗИ щитовидной железы; 9000"}
          className="h-64 w-full resize-none overflow-y-auto rounded-xl border border-line2 bg-surface2 p-3.5 font-mono text-sm leading-relaxed text-foreground outline-none transition-colors placeholder:text-faint focus:border-brand focus:bg-surface"
        />
        <p className="mt-2 text-xs text-faint">
          Формат:{" "}
          <code className="rounded bg-surface2 px-1.5 py-0.5 text-foreground">название; цена</code>.
          Цену можно и через пробел в конце строки - «УЗИ щитовидной железы 9000».
        </p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="w-full sm:w-64">
            <CityPicker
              value={city}
              cities={cities}
              onChange={setCity}
              size="sm"
              placeholder="Сравнить со всем рынком"
            />
          </div>
          <button
            onClick={run}
            disabled={loading || !text.trim()}
            className="h-11 rounded-xl bg-brand px-7 font-semibold text-white transition-colors hover:bg-brand-ink disabled:opacity-50"
          >
            {loading ? "Анализ…" : "Проверить"}
          </button>
        </div>
      </div>

      {results.length > 0 && (
        <div className="mt-8">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold tracking-tight text-foreground">Результат сравнения</h2>
            <div className="flex items-center gap-3 text-xs text-faint">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-deal" /> в рынке или дешевле
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-warn" /> дороже рынка
              </span>
            </div>
          </div>
          <div className="overflow-hidden rounded-2xl border border-line bg-surface">
          <table className="w-full text-sm">
            <thead className="bg-surface2 text-left text-xs uppercase tracking-wide text-faint">
              <tr>
                <th className="px-4 py-3 font-semibold">Строка прайса</th>
                <th className="px-4 py-3 font-semibold">Распознано</th>
                <th className="px-4 py-3 text-right font-semibold">Рынок</th>
                <th className="px-4 py-3 text-right font-semibold">Вердикт</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {results.map((r, i) => (
                <tr key={i} className="align-top hover:bg-surface2/60">
                  <td className="px-4 py-3">
                    <div className="text-foreground">{r.input}</div>
                    {r.input_price != null && (
                      <div className="mt-0.5 text-xs tabular-nums text-faint">ваша цена: {tenge(r.input_price)}</div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {r.matched ? (
                      <>
                        <div className="font-medium text-foreground">{r.matched.name}</div>
                        <div className="mt-0.5 text-xs text-faint">
                          {r.matched.method} · {(r.matched.score * 100).toFixed(0)}%
                        </div>
                      </>
                    ) : (
                      <span className="text-faint">не распознано</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {r.market ? (
                      <>
                        <div className="tabular-nums text-foreground">
                          {tenge(r.market.min)}–{tenge(r.market.max)}
                        </div>
                        <div className="mt-0.5 text-xs tabular-nums text-faint">
                          ср. {tenge(r.market.avg)} · {r.market.clinics} клиник
                        </div>
                      </>
                    ) : (
                      <span className="text-faint">нет данных</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <VerdictPill v={r.verdict} />
                    {r.vs_min_pct != null && (
                      <div className="mt-1 text-xs tabular-nums text-faint">+{r.vs_min_pct}% к минимуму</div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}
    </div>
  );
}
