"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { adminApi, ParseRunRow, ParseRunDetail, ParseScheduleRow } from "@/lib/api";

// Модуль сбора данных (ТЗ §3.1): расписание + ручной запуск + журнал прогонов,
// подробные логи и ошибки.
const STATUS_STYLE: Record<string, string> = {
  queued: "bg-warn-tint text-warn",
  running: "bg-brand/10 text-brand-ink",
  done: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
};

const LOG_STYLE: Record<string, string> = {
  info: "text-muted",
  warn: "text-warn",
  error: "text-red-600",
};

const ALMATY_OFFSET = 5; // Asia/Almaty = UTC+5

function fmt(ts: string | null) {
  if (!ts) return "-";
  const d = new Date(ts);
  return d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function fmtTime(ts: string | null) {
  if (!ts) return "";
  return new Date(ts).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtDuration(sec: number | null) {
  if (sec == null) return null;
  if (sec < 60) return `${sec.toFixed(0)} с`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m} мин ${s} с`;
}

// "HH:MM" по Алматы (UTC+5) -> {hour, minute} в UTC для API.
function almatyTimeToUtc(value: string): { hour: number; minute: number } | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(value.trim());
  if (!m) return null;
  const lh = Number(m[1]);
  const mm = Number(m[2]);
  if (lh < 0 || lh > 23 || mm < 0 || mm > 59) return null;
  return { hour: (lh - ALMATY_OFFSET + 24) % 24, minute: mm };
}

export default function ParserPage() {
  const { session } = useAuth();
  const token = session?.access_token ?? "";

  const [runs, setRuns] = useState<ParseRunRow[]>([]);
  const [detail, setDetail] = useState<ParseRunDetail | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [kind, setKind] = useState("web");
  const [limit, setLimit] = useState(200);
  const [hosts, setHosts] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  // расписание
  const [schedule, setSchedule] = useState<ParseScheduleRow | null>(null);
  const [schedTime, setSchedTime] = useState("07:30"); // по Алматы
  const [schedEnabled, setSchedEnabled] = useState(true);
  const [schedKind, setSchedKind] = useState("web");
  const [schedLimit, setSchedLimit] = useState(200);
  const [schedBusy, setSchedBusy] = useState(false);
  const [schedMsg, setSchedMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setRuns(await adminApi.runs(token));
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    }
  }, [token]);

  const loadSchedule = useCallback(async () => {
    if (!token) return;
    try {
      const s = await adminApi.schedule(token);
      setSchedule(s);
      setSchedTime(s.time_almaty);
      setSchedEnabled(s.enabled);
      setSchedKind(s.kind);
      setSchedLimit(s.run_limit);
    } catch (e) {
      setSchedMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    }
  }, [token]);

  useEffect(() => {
    load();
    loadSchedule();
  }, [load, loadSchedule]);

  // Пока есть незавершённые прогоны - мягкий поллинг статуса.
  useEffect(() => {
    if (!runs.some((r) => r.status === "queued" || r.status === "running")) return;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [runs, load]);

  // Если открыт прогон, который ещё идёт, - подтягиваем его логи.
  useEffect(() => {
    if (openId == null) return;
    const r = runs.find((x) => x.id === openId);
    if (!r || (r.status !== "running" && r.status !== "queued")) return;
    const t = setInterval(async () => {
      try {
        setDetail(await adminApi.run(token, openId));
      } catch {}
    }, 5000);
    return () => clearInterval(t);
  }, [openId, runs, token]);

  async function trigger() {
    if (!token) return;
    setBusy(true);
    setMsg(null);
    try {
      const res = await adminApi.trigger(token, {
        kind,
        limit,
        hosts: hosts.trim() || undefined,
      });
      setMsg({ kind: "ok", text: `Прогон #${res.run.id} поставлен в очередь (${res.run.trigger}).` });
      await load();
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }

  async function saveSchedule() {
    if (!token) return;
    const utc = almatyTimeToUtc(schedTime);
    if (!utc) {
      setSchedMsg({ kind: "err", text: "Время должно быть в формате ЧЧ:ММ." });
      return;
    }
    setSchedBusy(true);
    setSchedMsg(null);
    try {
      const s = await adminApi.saveSchedule(token, {
        enabled: schedEnabled,
        hour: utc.hour,
        minute: utc.minute,
        kind: schedKind,
        run_limit: schedLimit,
      });
      setSchedule(s);
      setSchedTime(s.time_almaty);
      setSchedMsg({
        kind: "ok",
        text: schedEnabled
          ? `Сохранено: ежедневно в ${s.time_almaty} (Алматы) · ${s.time_utc} UTC.`
          : "Сохранено: расписание выключено.",
      });
    } catch (e) {
      setSchedMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setSchedBusy(false);
    }
  }

  async function toggle(id: number) {
    if (openId === id) {
      setOpenId(null);
      setDetail(null);
      return;
    }
    setOpenId(id);
    setDetail(null);
    try {
      setDetail(await adminApi.run(token, id));
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    }
  }

  return (
    <div className="space-y-6">
      {/* расписание ежедневного парсинга */}
      <section className="rounded-2xl border border-line bg-surface p-5">
        <h2 className="text-base font-semibold text-foreground">Расписание ежедневного парсинга</h2>
        <p className="mt-1 text-sm text-muted">
          Парсер запускается каждый день в указанное время. Время задаётся здесь и хранится в БД -
          менять YAML не нужно. Раннер будится каждые {schedule?.step_minutes ?? 30} мин и стартует сбор
          в ближайшее окно после выбранного времени.
        </p>
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={schedEnabled}
              onChange={(e) => setSchedEnabled(e.target.checked)}
              className="h-4 w-4"
            />
            <span className="text-foreground">Включено</span>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-muted">Время (Алматы, UTC+5)</span>
            <input
              type="time"
              value={schedTime}
              onChange={(e) => setSchedTime(e.target.value)}
              className="rounded-lg border border-line2 bg-surface px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-muted">Источники</span>
            <select
              value={schedKind}
              onChange={(e) => setSchedKind(e.target.value)}
              className="rounded-lg border border-line2 bg-surface px-3 py-2"
            >
              <option value="web">web (103.kz)</option>
              <option value="file">file (PDF/DOCX/XLSX)</option>
            </select>
          </label>
          {schedKind === "web" && (
            <label className="text-sm">
              <span className="mb-1 block text-muted">Лимит хостов</span>
              <input
                type="number"
                value={schedLimit}
                min={1}
                onChange={(e) => setSchedLimit(Number(e.target.value))}
                className="w-28 rounded-lg border border-line2 bg-surface px-3 py-2"
              />
            </label>
          )}
          <button
            onClick={saveSchedule}
            disabled={schedBusy || !token}
            className="rounded-xl bg-brand px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand/90 disabled:opacity-60"
          >
            {schedBusy ? "Сохраняем…" : "Сохранить"}
          </button>
        </div>
        <p className="mt-2 text-xs text-faint">
          {schedule
            ? `Сейчас: ${schedule.enabled ? "включено" : "выключено"} · ${schedule.time_almaty} Алматы (${schedule.time_utc} UTC)`
            : "Загружаем…"}
        </p>
        {schedMsg && (
          <p className={`mt-2 text-sm ${schedMsg.kind === "ok" ? "text-emerald-600" : "text-warn"}`}>
            {schedMsg.text}
          </p>
        )}
      </section>

      {/* запуск */}
      <section className="rounded-2xl border border-line bg-surface p-5">
        <h2 className="text-base font-semibold text-foreground">Запустить сбор данных</h2>
        <p className="mt-1 text-sm text-muted">
          Парсинг выполняется на раннере (GitHub Actions) - тем же воркером, что и по расписанию.
          Здесь ставим прогон в очередь вручную.
        </p>
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="mb-1 block text-muted">Источники</span>
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              className="rounded-lg border border-line2 bg-surface px-3 py-2"
            >
              <option value="web">web (103.kz)</option>
              <option value="file">file (PDF/DOCX/XLSX)</option>
            </select>
          </label>
          {kind === "web" && (
            <label className="text-sm">
              <span className="mb-1 block text-muted">Лимит хостов</span>
              <input
                type="number"
                value={limit}
                min={1}
                onChange={(e) => setLimit(Number(e.target.value))}
                className="w-28 rounded-lg border border-line2 bg-surface px-3 py-2"
              />
            </label>
          )}
          {kind === "web" && (
            <label className="grow text-sm">
              <span className="mb-1 block text-muted">Хосты через запятую (опц., вместо frontier)</span>
              <input
                value={hosts}
                onChange={(e) => setHosts(e.target.value)}
                placeholder="kdl.103.kz, invitro.103.kz"
                className="w-full rounded-lg border border-line2 bg-surface px-3 py-2"
              />
            </label>
          )}
          <button
            onClick={trigger}
            disabled={busy || !token}
            className="rounded-xl bg-brand px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand/90 disabled:opacity-60"
          >
            {busy ? "Ставим…" : "Запустить"}
          </button>
        </div>
        {msg && (
          <p className={`mt-3 text-sm ${msg.kind === "ok" ? "text-emerald-600" : "text-warn"}`}>{msg.text}</p>
        )}
      </section>

      {/* журнал прогонов */}
      <section className="rounded-2xl border border-line bg-surface">
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 className="text-base font-semibold text-foreground">Журнал прогонов</h2>
          <button onClick={load} className="text-sm text-brand hover:underline">
            Обновить
          </button>
        </div>
        {runs.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-muted">Прогонов пока нет.</p>
        ) : (
          <div className="divide-y divide-line">
            {runs.map((r) => (
              <div key={r.id}>
                <button
                  onClick={() => toggle(r.id)}
                  className="grid w-full grid-cols-[auto_1fr_auto] items-center gap-3 px-5 py-3 text-left hover:bg-surface2"
                >
                  <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${STATUS_STYLE[r.status] ?? "bg-surface2 text-muted"}`}>
                    {r.status}
                  </span>
                  <span className="min-w-0 text-sm">
                    <span className="font-medium text-foreground">#{r.id}</span>{" "}
                    <span className="text-muted">
                      {r.source_kind} · {r.trigger} · старт {fmt(r.started_at)}
                      {r.finished_at ? ` · финиш ${fmt(r.finished_at)}` : ""}
                      {fmtDuration(r.duration_sec) ? ` · ${fmtDuration(r.duration_sec)}` : ""}
                    </span>
                    <span className="block truncate text-xs text-faint">
                      источников {r.sources_ok}/{r.sources_total} · ошибок {r.sources_failed} · строк {r.rows_raw}{" "}
                      (новых {r.rows_new}, дублей {r.rows_dup})
                    </span>
                  </span>
                  <span className="text-xs text-faint">{openId === r.id ? "▲" : "▼"}</span>
                </button>
                {openId === r.id && (
                  <div className="space-y-4 bg-surface2/50 px-5 py-3 text-sm">
                    {!detail ? (
                      <p className="text-muted">Загружаем…</p>
                    ) : (
                      <>
                        {/* подробные логи прогона */}
                        <div>
                          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">
                            Подробный лог
                          </p>
                          {detail.logs.length === 0 ? (
                            <p className="text-muted">Лог пуст.</p>
                          ) : (
                            <div className="max-h-72 overflow-auto rounded-lg border border-line bg-surface p-2 font-mono text-xs leading-relaxed">
                              {detail.logs.map((l, i) => (
                                <div key={i} className="flex gap-2">
                                  <span className="shrink-0 text-faint">{fmtTime(l.ts)}</span>
                                  <span className={`${LOG_STYLE[l.level] ?? "text-muted"} min-w-0`}>
                                    {l.source ? <span className="text-foreground">{l.source} </span> : null}
                                    {l.message}
                                  </span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>

                        {/* ошибки по источникам */}
                        <div>
                          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-faint">
                            Ошибки ({detail.errors.length})
                          </p>
                          {detail.errors.length === 0 ? (
                            <p className="text-emerald-600">Ошибок не зафиксировано.</p>
                          ) : (
                            <table className="w-full text-left text-xs">
                              <thead className="text-faint">
                                <tr>
                                  <th className="py-1 pr-3 font-medium">Источник</th>
                                  <th className="py-1 pr-3 font-medium">Стадия</th>
                                  <th className="py-1 font-medium">Причина</th>
                                </tr>
                              </thead>
                              <tbody className="align-top">
                                {detail.errors.map((e, i) => (
                                  <tr key={i} className="border-t border-line">
                                    <td className="py-1 pr-3 font-mono text-foreground">{e.source}</td>
                                    <td className="py-1 pr-3 text-muted">{e.stage}</td>
                                    <td className="py-1 text-muted">{e.error}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
