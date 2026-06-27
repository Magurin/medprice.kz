"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  adminApi,
  api,
  AdminClinic,
  ImportPreview,
  ImportPreviewRow,
  ImportCommitRow,
  ServiceRow,
} from "@/lib/api";

// Мастер импорта прайс-листа: загрузить HTML/PDF/DOCX/Excel или ссылку -> авто-распознавание
// строк и сопоставление с услугами -> правка модератором -> запись в каталог (ТЗ §3.1/3.2).

type Decision = "match" | "create" | "skip";
interface EditRow {
  raw_name: string;
  price: number | null;
  decision: Decision;
  service_code: string | null;
  service_name: string; // для создания новой
  category: string;
  matched_name: string | null;
  method: string | null;
}

function toEditRow(r: ImportPreviewRow): EditRow {
  let decision: Decision = "create";
  if (r.known_skip) decision = "skip";
  else if (r.match) decision = "match";
  return {
    raw_name: r.raw_name,
    price: r.price,
    decision,
    service_code: r.match?.code ?? null,
    service_name: r.match?.name ?? r.raw_name,
    category: r.match?.category ?? "",
    matched_name: r.match?.name ?? null,
    method: r.match?.method ?? null,
  };
}

const METHOD_LABEL: Record<string, string> = {
  curated: "справочник",
  curated_fuzzy: "справочник~",
  learned: "ваше решение",
  auto: "по названию",
};

function ServiceSearch({ onPick }: { onPick: (s: ServiceRow) => void }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<ServiceRow[]>([]);
  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) {
      setResults([]);
      return;
    }
    let alive = true;
    const t = setTimeout(async () => {
      try {
        const r = await api.services({ q: term, limit: 6 });
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
  return (
    <div className="mt-1">
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Найти услугу в справочнике…"
        className="w-full rounded border border-line2 bg-surface px-2 py-1 text-sm"
      />
      {results.length > 0 && (
        <ul className="mt-1 divide-y divide-line rounded border border-line bg-surface">
          {results.map((s) => (
            <li key={s.code}>
              <button
                onClick={() => {
                  onPick(s);
                  setQ("");
                  setResults([]);
                }}
                className="block w-full px-2 py-1 text-left text-sm hover:bg-surface2"
              >
                <span className="font-medium text-foreground">{s.name}</span>
                <span className="ml-2 text-xs text-faint">{s.category || "—"}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RowEditor({ row, onChange }: { row: EditRow; onChange: (r: EditRow) => void }) {
  const [picking, setPicking] = useState(false);
  const set = (patch: Partial<EditRow>) => onChange({ ...row, ...patch });

  return (
    <tr className={`border-t border-line align-top ${row.decision === "skip" ? "opacity-50" : ""}`}>
      <td className="py-2 pr-3">
        <input
          value={row.raw_name}
          onChange={(e) => set({ raw_name: e.target.value })}
          className="w-full rounded border border-line2 bg-surface px-2 py-1 text-sm"
        />
      </td>
      <td className="py-2 pr-3">
        <input
          value={row.price ?? ""}
          onChange={(e) => set({ price: e.target.value === "" ? null : Number(e.target.value) })}
          inputMode="numeric"
          placeholder="по запросу"
          className="w-24 rounded border border-line2 bg-surface px-2 py-1 text-sm"
        />
      </td>
      <td className="py-2 pr-3">
        {row.decision === "skip" ? (
          <span className="text-sm text-faint">пропущено</span>
        ) : row.decision === "create" ? (
          <div>
            <input
              value={row.service_name}
              onChange={(e) => set({ service_name: e.target.value })}
              placeholder="Название новой услуги"
              className="w-full rounded border border-line2 bg-surface px-2 py-1 text-sm"
            />
            <input
              value={row.category}
              onChange={(e) => set({ category: e.target.value })}
              placeholder="Категория (опц.)"
              className="mt-1 w-full rounded border border-line2 bg-surface px-2 py-1 text-xs"
            />
            <span className="mt-0.5 block text-xs text-faint">новая каноническая услуга</span>
          </div>
        ) : (
          <div>
            <span className="text-sm font-medium text-foreground">{row.matched_name}</span>
            {row.method && (
              <span className="ml-2 rounded bg-surface2 px-1.5 py-0.5 text-xs text-muted">
                {METHOD_LABEL[row.method] ?? row.method}
              </span>
            )}
            {picking && (
              <ServiceSearch
                onPick={(s) => {
                  set({ service_code: s.code, matched_name: s.name, method: "manual" });
                  setPicking(false);
                }}
              />
            )}
          </div>
        )}
      </td>
      <td className="py-2 text-xs">
        <div className="flex flex-col items-start gap-0.5">
          {row.decision !== "match" && (
            <button onClick={() => set({ decision: "match" })} className="text-brand hover:underline" disabled={!row.service_code && !row.matched_name}>
              привязать
            </button>
          )}
          {row.decision === "match" && (
            <button onClick={() => setPicking((p) => !p)} className="text-muted hover:text-foreground">
              сменить услугу
            </button>
          )}
          {row.decision !== "create" && (
            <button onClick={() => set({ decision: "create" })} className="text-muted hover:text-foreground">
              новая услуга
            </button>
          )}
          {row.decision !== "skip" ? (
            <button onClick={() => set({ decision: "skip" })} className="text-muted hover:text-warn">
              пропустить
            </button>
          ) : (
            <button onClick={() => set({ decision: row.matched_name ? "match" : "create" })} className="text-brand hover:underline">
              вернуть
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}

function ImportInner() {
  const { session } = useAuth();
  const token = session?.access_token ?? "";
  const params = useSearchParams();

  const [clinics, setClinics] = useState<AdminClinic[]>([]);
  const [clinicId, setClinicId] = useState<number | "">("");
  const [mode, setMode] = useState<"file" | "url">("file");
  const [url, setUrl] = useState("");
  const [replace, setReplace] = useState(false);

  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [rows, setRows] = useState<EditRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  useEffect(() => {
    if (!token) return;
    adminApi
      .clinics(token, undefined, 200)
      .then((r) => {
        setClinics(r.items);
        const pre = params.get("clinic");
        if (pre && r.items.some((c) => c.id === Number(pre))) setClinicId(Number(pre));
      })
      .catch((e) => setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) }));
  }, [token, params]);

  const applyPreview = useCallback((p: ImportPreview) => {
    setPreview(p);
    setRows(p.rows.map(toEditRow));
    setMsg({
      kind: "ok",
      text: `Распознано строк: ${p.total}, авто-сопоставлено со справочником: ${p.auto_matched}. Проверьте и подтвердите.`,
    });
  }, []);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setMsg(null);
    try {
      applyPreview(await adminApi.importFile(token, file));
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  async function onUrl() {
    if (!url.trim()) return;
    setBusy(true);
    setMsg(null);
    try {
      applyPreview(await adminApi.importUrl(token, url.trim()));
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  }

  async function commit() {
    if (!clinicId) {
      setMsg({ kind: "err", text: "Сначала выберите клинику." });
      return;
    }
    const payload: ImportCommitRow[] = rows.map((r) => ({
      raw_name: r.raw_name,
      price: r.price,
      skip: r.decision === "skip",
      create_new: r.decision === "create",
      service_name: r.decision === "create" ? r.service_name : undefined,
      category: r.category || undefined,
      service_code: r.decision === "match" ? r.service_code ?? undefined : undefined,
    }));
    setBusy(true);
    setMsg(null);
    try {
      const res = await adminApi.importCommit(token, {
        clinic_id: Number(clinicId),
        source: preview?.source,
        replace,
        rows: payload,
      });
      setMsg({
        kind: "ok",
        text: `Готово: в «${res.clinic}» добавлено цен ${res.offers_created}, новых услуг ${res.services_created}.`,
      });
      setPreview(null);
      setRows([]);
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  }

  const willImport = rows.filter((r) => r.decision !== "skip").length;

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-line bg-surface p-5">
        <h2 className="text-base font-semibold text-foreground">Импорт прайс-листа</h2>
        <p className="mt-1 text-sm text-muted">
          Загрузите файл (Excel, PDF, Word, HTML) или ссылку на страницу с ценами. Система распознает
          строки и подберёт услуги — вы проверите и поправите перед записью.
        </p>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="text-sm">
            <span className="mb-1 block text-muted">Клиника назначения *</span>
            <select
              value={clinicId}
              onChange={(e) => setClinicId(e.target.value ? Number(e.target.value) : "")}
              className="w-full rounded-lg border border-line2 bg-surface px-3 py-2 text-sm"
            >
              <option value="">— выберите клинику —</option>
              {clinics.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                  {c.city ? ` (${c.city})` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-end gap-2 text-sm text-muted">
            <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} className="mb-2.5" />
            <span className="mb-2">Заменить прежде импортированные цены этой клиники</span>
          </label>
        </div>

        <div className="mt-4 flex gap-1 text-sm font-medium">
          <button
            onClick={() => setMode("file")}
            className={`rounded-lg px-3 py-1.5 ${mode === "file" ? "bg-surface2 text-brand-ink" : "text-muted hover:bg-surface2"}`}
          >
            Файл
          </button>
          <button
            onClick={() => setMode("url")}
            className={`rounded-lg px-3 py-1.5 ${mode === "url" ? "bg-surface2 text-brand-ink" : "text-muted hover:bg-surface2"}`}
          >
            Ссылка
          </button>
        </div>

        <div className="mt-3">
          {mode === "file" ? (
            <input
              type="file"
              accept=".xlsx,.xls,.docx,.pdf,.html,.htm"
              onChange={onFile}
              disabled={busy}
              className="block w-full text-sm text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-brand file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-brand/90"
            />
          ) : (
            <div className="flex gap-2">
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://clinic.kz/price.html"
                className="grow rounded-lg border border-line2 bg-surface px-3 py-2 text-sm"
              />
              <button
                onClick={onUrl}
                disabled={busy || !url.trim()}
                className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand/90 disabled:opacity-60"
              >
                {busy ? "Читаем…" : "Распознать"}
              </button>
            </div>
          )}
        </div>

        {busy && mode === "file" && <p className="mt-2 text-sm text-muted">Распознаём файл…</p>}
        {msg && (
          <p className={`mt-3 text-sm ${msg.kind === "ok" ? "text-emerald-600" : "text-warn"}`}>{msg.text}</p>
        )}
      </section>

      {preview && (
        <section className="rounded-2xl border border-line bg-surface">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-5 py-3">
            <h3 className="text-sm font-semibold text-foreground">
              Предпросмотр: {rows.length} строк · к импорту {willImport}
            </h3>
            <button
              onClick={commit}
              disabled={busy || !clinicId || willImport === 0}
              className="rounded-xl bg-brand px-5 py-2 text-sm font-semibold text-white hover:bg-brand/90 disabled:opacity-60"
            >
              {busy ? "Записываем…" : `Импортировать (${willImport})`}
            </button>
          </div>
          <div className="overflow-x-auto px-5 py-3">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-faint">
                <tr>
                  <th className="py-1 pr-3 font-medium">Строка прайса</th>
                  <th className="py-1 pr-3 font-medium">Цена, ₸</th>
                  <th className="py-1 pr-3 font-medium">Услуга</th>
                  <th className="py-1 font-medium">Действие</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <RowEditor key={i} row={r} onChange={(nr) => setRows((rs) => rs.map((x, j) => (j === i ? nr : x)))} />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

export default function ImportPage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Загрузка…</p>}>
      <ImportInner />
    </Suspense>
  );
}
