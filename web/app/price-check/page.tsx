"use client";

import { useEffect, useState } from "react";
import { api, CityRow, MatchResult, tenge } from "@/lib/api";
import CityPicker from "@/components/CityPicker";

const SAMPLE = `Клинический анализ крови (с лейкоцитарной формулой); 2500
ТТГ ультрачувствительный; 1500
МРТ артерий и вен головного мозга; 40000
УЗИ щитовидной железы; 9000`;

function VerdictPill({ v }: { v?: string }) {
  if (!v) return <span className="text-faint">—</span>;
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
      .map((l) => {
        const idx = l.lastIndexOf(";");
        if (idx === -1) return { name: l };
        const name = l.slice(0, idx).trim();
        const price = parseInt(l.slice(idx + 1).replace(/\D/g, ""), 10);
        return { name, price: Number.isNaN(price) ? undefined : price };
      });
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
        Проверить прайс по рынку
      </h1>
      <p className="mt-2 max-w-2xl text-muted">
        Вставьте строки прайса в формате{" "}
        <code className="rounded bg-surface2 px-1.5 py-0.5 text-sm text-foreground">название; цена</code>{" "}
        (по одной в строке). Система распознает услугу, приведёт к справочнику и сравнит с
        рынком — даже если названия у клиник разные.
      </p>

      <div className="mt-5 rounded-2xl border border-line bg-surface p-4">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={6}
          spellCheck={false}
          className="w-full resize-y rounded-xl border border-line2 bg-surface2 p-3.5 font-mono text-sm text-foreground outline-none transition-colors focus:border-brand focus:bg-surface"
        />
        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="w-full sm:w-56">
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
            disabled={loading}
            className="h-11 rounded-xl bg-brand px-7 font-semibold text-white transition-colors hover:bg-brand-ink disabled:opacity-50"
          >
            {loading ? "Анализ…" : "Проверить"}
          </button>
        </div>
      </div>

      {results.length > 0 && (
        <div className="mt-6 overflow-hidden rounded-2xl border border-line bg-surface">
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
      )}
    </div>
  );
}
