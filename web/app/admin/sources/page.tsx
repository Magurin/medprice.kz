"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { adminApi, ParseSourceRow } from "@/lib/api";

// Управление источниками парсинга (ТЗ §3.1): список целевых сайтов, вкл/выкл, добавление.
function whenLabel(iso: string | null) {
  if (!iso) return "ещё не запускался";
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

export default function SourcesPage() {
  const { session } = useAuth();
  const token = session?.access_token ?? "";

  const [rows, setRows] = useState<ParseSourceRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [host, setHost] = useState("");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      setRows(await adminApi.sources(token));
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function toggle(s: ParseSourceRow) {
    try {
      const upd = await adminApi.patchSource(token, s.id, { enabled: !s.enabled });
      setRows((rs) => rs.map((r) => (r.id === s.id ? upd : r)));
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    }
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!host.trim()) return;
    setBusy(true);
    setMsg(null);
    try {
      const s = await adminApi.addSource(token, { value: host.trim(), label: label.trim() || undefined });
      setRows((rs) => [...rs, s]);
      setHost("");
      setLabel("");
      setMsg({ kind: "ok", text: `Источник «${s.label || s.value}» добавлен.` });
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }

  async function remove(s: ParseSourceRow) {
    if (!confirm(`Удалить источник «${s.label || s.value}»?`)) return;
    try {
      await adminApi.deleteSource(token, s.id);
      setRows((rs) => rs.filter((r) => r.id !== s.id));
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    }
  }

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-line bg-surface p-5">
        <h2 className="text-base font-semibold text-foreground">Источники парсинга</h2>
        <p className="mt-1 text-sm text-muted">
          Сайты, с которых собираются прайсы. Выключенные источники пропускаются при запуске.
          «103.kz» — авто-список всех клиник портала; отдельные сайты можно добавить вручную.
        </p>

        <form onSubmit={add} className="mt-4 flex flex-wrap items-end gap-2">
          <label className="grow text-sm">
            <span className="mb-1 block text-muted">Новый источник (хост)</span>
            <input
              value={host}
              onChange={(e) => setHost(e.target.value)}
              placeholder="например, kdl.103.kz"
              className="w-full rounded-lg border border-line2 bg-surface px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-muted">Название (опц.)</span>
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="KDL"
              className="w-40 rounded-lg border border-line2 bg-surface px-3 py-2"
            />
          </label>
          <button
            disabled={busy || !host.trim()}
            className="rounded-xl bg-brand px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand/90 disabled:opacity-60"
          >
            Добавить
          </button>
        </form>
        <p className="mt-2 text-xs text-faint">
          Сейчас извлечение заточено под шаблон 103.kz — хосты вида <code>name.103.kz</code> парсятся
          корректно. Сайты с другой структурой потребуют отдельного парсера (ошибки видны в журнале прогонов).
        </p>
        {msg && (
          <p className={`mt-3 text-sm ${msg.kind === "ok" ? "text-emerald-600" : "text-warn"}`}>{msg.text}</p>
        )}
      </section>

      <section className="rounded-2xl border border-line bg-surface">
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <h3 className="text-sm font-semibold text-foreground">
            Всего источников: <span className="text-brand-ink">{rows.length}</span>
          </h3>
          <button onClick={load} className="text-sm text-brand hover:underline">Обновить</button>
        </div>

        {loading ? (
          <p className="px-5 py-8 text-center text-sm text-muted">Загружаем…</p>
        ) : rows.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-muted">Источников нет.</p>
        ) : (
          <div className="divide-y divide-line">
            {rows.map((s) => (
              <div key={s.id} className="flex items-center gap-3 px-5 py-3">
                {/* toggle */}
                <button
                  onClick={() => toggle(s)}
                  title={s.enabled ? "Выключить" : "Включить"}
                  className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${
                    s.enabled ? "bg-brand" : "bg-line2"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${
                      s.enabled ? "left-[18px]" : "left-0.5"
                    }`}
                  />
                </button>

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium text-foreground">{s.label || s.value}</span>
                    {s.kind === "frontier" && (
                      <span className="shrink-0 rounded-full bg-surface2 px-2 py-0.5 text-[11px] font-semibold text-muted">
                        авто · {s.frontier_size?.toLocaleString("ru-RU")} хостов
                      </span>
                    )}
                  </div>
                  <div className="truncate text-xs text-faint">
                    {s.value} · посл. запуск: {whenLabel(s.last_run_at)}
                  </div>
                </div>

                {s.kind === "host" ? (
                  <button
                    onClick={() => remove(s)}
                    className="shrink-0 rounded-lg px-2.5 py-1.5 text-xs text-muted hover:bg-warn-tint hover:text-warn"
                  >
                    Удалить
                  </button>
                ) : (
                  <span className="shrink-0 px-2.5 py-1.5 text-xs text-faint">базовый</span>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
