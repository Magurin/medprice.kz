"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { api, adminApi, UnmatchedGroup, ServiceRow, tenge } from "@/lib/api";

// Очередь ручной разметки (ТЗ §3.2): строки прайсов, которые матчер не привязал.
// Модератор находит каноническую услугу и привязывает - цена попадает в сравнение.
function priceLabel(g: UnmatchedGroup) {
  if (g.min_price == null) return "цена не распознана";
  if (g.max_price && g.max_price !== g.min_price) return `${tenge(g.min_price)} – ${tenge(g.max_price)}`;
  return tenge(g.min_price);
}

function AssignPanel({
  raw,
  token,
  onDone,
}: {
  raw: string;
  token: string;
  onDone: (msg: string) => void;
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<ServiceRow[]>([]);
  const [busy, setBusy] = useState(false);

  // поиск канонических услуг по мере ввода
  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) {
      setResults([]);
      return;
    }
    let alive = true;
    const t = setTimeout(async () => {
      try {
        const r = await api.services({ q: term, limit: 8 });
        if (alive) setResults(r);
      } catch {
        /* игнор */
      }
    }, 250);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [q]);

  async function assign(code: string, name: string) {
    setBusy(true);
    try {
      const res = await adminApi.assignMatch(token, raw, code);
      onDone(`Привязано к «${name}»: закрыто ${res.rows_closed}, создано цен ${res.offers_created}.`);
    } catch (e) {
      onDone(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function skip() {
    setBusy(true);
    try {
      const res = await adminApi.skipMatch(token, raw);
      onDone(`Помечено «не услуга»: убрано ${res.rows_closed}.`);
    } catch (e) {
      onDone(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bg-surface2/50 px-5 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Найти каноническую услугу: «общий анализ крови»…"
          className="min-w-[260px] grow rounded-lg border border-line2 bg-surface px-3 py-2 text-sm"
        />
        <button
          onClick={skip}
          disabled={busy}
          className="rounded-lg border border-line2 px-3 py-2 text-sm text-muted hover:border-warn hover:text-warn disabled:opacity-60"
        >
          Не услуга
        </button>
      </div>
      {results.length > 0 && (
        <ul className="mt-2 divide-y divide-line rounded-lg border border-line bg-surface">
          {results.map((s) => (
            <li key={s.code}>
              <button
                onClick={() => assign(s.code, s.name)}
                disabled={busy}
                className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-surface2 disabled:opacity-60"
              >
                <span className="min-w-0">
                  <span className="font-medium text-foreground">{s.name}</span>
                  <span className="block truncate text-xs text-faint">
                    {s.category || "без категории"} · {s.clinics} клиник · {s.is_curated ? "справочник" : "авто"}
                  </span>
                </span>
                <span className="shrink-0 text-xs font-semibold text-brand">привязать →</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {q.trim().length >= 2 && results.length === 0 && (
        <p className="mt-2 text-xs text-faint">Ничего не нашлось - уточни запрос.</p>
      )}
    </div>
  );
}

export default function QueuePage() {
  const { session } = useAuth();
  const token = session?.access_token ?? "";

  const [groups, setGroups] = useState<UnmatchedGroup[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(
    async (term: string) => {
      if (!token) return;
      setLoading(true);
      try {
        const r = await adminApi.unmatched(token, term || undefined);
        setGroups(r.items);
        setTotal(r.total);
      } catch (e) {
        setMsg(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [token]
  );

  useEffect(() => {
    load("");
  }, [load]);

  function afterAction(text: string, raw: string) {
    setMsg(text);
    setOpen(null);
    // убираем закрытую строку из списка локально + обновляем счётчик
    setGroups((gs) => gs.filter((g) => g.raw_name !== raw));
    setTotal((t) => Math.max(0, t - 1));
  }

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-line bg-surface p-5">
        <h2 className="text-base font-semibold text-foreground">Очередь ручной разметки</h2>
        <p className="mt-1 text-sm text-muted">
          Строки прайсов, которые автоматический матчер не привязал к справочнику. Найди для строки
          каноническую услугу - её цена сразу попадёт в сравнение. Решение запоминается.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            load(q);
          }}
          className="mt-4 flex gap-2"
        >
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Фильтр по названию строки…"
            className="grow rounded-lg border border-line2 bg-surface px-3 py-2 text-sm"
          />
          <button className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand/90">
            Найти
          </button>
        </form>
        {msg && <p className="mt-3 text-sm text-emerald-600">{msg}</p>}
      </section>

      <section className="rounded-2xl border border-line bg-surface">
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <h3 className="text-sm font-semibold text-foreground">
            Непривязанных названий: <span className="text-brand-ink">{total.toLocaleString("ru-RU")}</span>
          </h3>
          <button onClick={() => load(q)} className="text-sm text-brand hover:underline">
            Обновить
          </button>
        </div>

        {loading ? (
          <p className="px-5 py-8 text-center text-sm text-muted">Загружаем…</p>
        ) : groups.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-muted">Очередь пуста 🎉</p>
        ) : (
          <div className="divide-y divide-line">
            {groups.map((g) => (
              <div key={g.raw_name}>
                <button
                  onClick={() => setOpen(open === g.raw_name ? null : g.raw_name)}
                  className="grid w-full grid-cols-[1fr_auto_auto] items-center gap-3 px-5 py-3 text-left hover:bg-surface2"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-foreground">{g.raw_name}</span>
                    <span className="text-xs text-faint">{priceLabel(g)}</span>
                  </span>
                  {g.count > 1 && (
                    <span className="rounded-full bg-surface2 px-2 py-0.5 text-xs font-semibold text-muted">
                      ×{g.count}
                    </span>
                  )}
                  <span className="text-xs font-semibold text-brand">{open === g.raw_name ? "закрыть" : "разметить"}</span>
                </button>
                {open === g.raw_name && (
                  <AssignPanel raw={g.raw_name} token={token} onDone={(m) => afterAction(m, g.raw_name)} />
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
