"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { adminApi, api, AdminClinic, AdminOffer, ServiceRow } from "@/lib/api";

// Ведение клиник модераторами: добавить/поправить/удалить клинику и её цены вручную
// (ТЗ §3.2). Для массовой загрузки прайса есть отдельный мастер импорта (/admin/import).

const EMPTY = {
  name: "",
  city: "",
  address: "",
  phone: "",
  working_hours: "",
  source_url: "",
};

// --- поиск канонической услуги (для привязки строки прайса) ---
function ServicePicker({ onPick }: { onPick: (s: ServiceRow) => void }) {
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
  return (
    <div>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Найти услугу в справочнике…"
        className="w-full rounded-lg border border-line2 bg-surface px-3 py-2 text-sm"
      />
      {results.length > 0 && (
        <ul className="mt-1 divide-y divide-line rounded-lg border border-line bg-surface">
          {results.map((s) => (
            <li key={s.code}>
              <button
                onClick={() => {
                  onPick(s);
                  setQ("");
                  setResults([]);
                }}
                className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-surface2"
              >
                <span className="min-w-0 truncate">
                  <span className="font-medium text-foreground">{s.name}</span>
                  <span className="block truncate text-xs text-faint">
                    {s.category || "без категории"} · {s.clinics} клиник
                  </span>
                </span>
                <span className="shrink-0 text-xs font-semibold text-brand">выбрать →</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// --- цены одной клиники: список + правка + добавление ---
function OffersPanel({ clinic, token }: { clinic: AdminClinic; token: string }) {
  const [offers, setOffers] = useState<AdminOffer[]>([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);

  // форма новой строки прайса
  const [raw, setRaw] = useState("");
  const [price, setPrice] = useState("");
  const [pick, setPick] = useState<ServiceRow | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminApi.clinicOffers(token, clinic.id);
      setOffers(r.offers);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [token, clinic.id]);

  useEffect(() => {
    load();
  }, [load]);

  async function addOffer() {
    if (!raw.trim()) return;
    try {
      await adminApi.createOffer(token, {
        clinic_id: clinic.id,
        raw_name: raw.trim(),
        price: price ? Number(price) : null,
        service_code: pick?.code,
      });
      setRaw("");
      setPrice("");
      setPick(null);
      setMsg("Добавлено.");
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function savePrice(o: AdminOffer, value: string) {
    const v = value.trim() === "" ? null : Number(value);
    if (v === o.price) return;
    try {
      await adminApi.patchOffer(token, o.id, { price: v, on_request: v === null });
      setOffers((os) => os.map((x) => (x.id === o.id ? { ...x, price: v, on_request: v === null } : x)));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function remove(o: AdminOffer) {
    if (!confirm(`Удалить строку «${o.raw_name}»?`)) return;
    try {
      await adminApi.deleteOffer(token, o.id);
      setOffers((os) => os.filter((x) => x.id !== o.id));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="bg-surface2/50 px-5 py-4">
      {/* добавить строку */}
      <div className="rounded-xl border border-line bg-surface p-3">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">Добавить услугу + цену</p>
        <div className="flex flex-wrap items-start gap-2">
          <input
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            placeholder="Название как в прайсе клиники"
            className="min-w-[220px] grow rounded-lg border border-line2 bg-surface px-3 py-2 text-sm"
          />
          <input
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            inputMode="numeric"
            placeholder="₸"
            className="w-28 rounded-lg border border-line2 bg-surface px-3 py-2 text-sm"
          />
          <button
            onClick={addOffer}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand/90"
          >
            Добавить
          </button>
        </div>
        <div className="mt-2">
          {pick ? (
            <p className="text-xs text-muted">
              Привязка: <span className="font-medium text-foreground">{pick.name}</span>{" "}
              <button onClick={() => setPick(null)} className="text-brand hover:underline">
                сменить
              </button>
            </p>
          ) : (
            <>
              <p className="mb-1 text-xs text-faint">
                Не обязательно: привяжите к услуге справочника (иначе подберём автоматически).
              </p>
              <ServicePicker onPick={setPick} />
            </>
          )}
        </div>
      </div>

      {msg && <p className="mt-2 text-xs text-emerald-600">{msg}</p>}

      {/* список цен */}
      {loading ? (
        <p className="py-4 text-center text-sm text-muted">Загружаем цены…</p>
      ) : offers.length === 0 ? (
        <p className="py-4 text-center text-sm text-muted">У клиники пока нет цен.</p>
      ) : (
        <table className="mt-3 w-full text-left text-sm">
          <thead className="text-xs text-faint">
            <tr>
              <th className="py-1 pr-3 font-medium">Строка прайса</th>
              <th className="py-1 pr-3 font-medium">Услуга</th>
              <th className="py-1 pr-3 font-medium">Цена</th>
              <th className="py-1 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {offers.map((o) => (
              <tr key={o.id} className="border-t border-line align-top">
                <td className="py-1.5 pr-3 text-foreground">{o.raw_name}</td>
                <td className="py-1.5 pr-3 text-muted">
                  {o.service_name}
                  <span className="block text-xs text-faint">{o.category || "—"}</span>
                </td>
                <td className="py-1.5 pr-3">
                  <input
                    defaultValue={o.price ?? ""}
                    onBlur={(e) => savePrice(o, e.target.value)}
                    inputMode="numeric"
                    placeholder="по запросу"
                    className="w-24 rounded border border-line2 bg-surface px-2 py-1 text-sm"
                  />
                </td>
                <td className="py-1.5">
                  <button
                    onClick={() => remove(o)}
                    className="text-xs text-muted hover:text-warn"
                    title="Удалить"
                  >
                    удалить
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// --- форма клиники (создание/редактирование) ---
function ClinicForm({
  initial,
  onSubmit,
  onCancel,
  submitLabel,
}: {
  initial: typeof EMPTY;
  onSubmit: (v: typeof EMPTY) => Promise<void>;
  onCancel: () => void;
  submitLabel: string;
}) {
  const [v, setV] = useState(initial);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setV((s) => ({ ...s, [k]: e.target.value }));
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      <input value={v.name} onChange={set("name")} placeholder="Название клиники *" className="rounded-lg border border-line2 bg-surface px-3 py-2 text-sm sm:col-span-2" />
      <input value={v.city} onChange={set("city")} placeholder="Город" className="rounded-lg border border-line2 bg-surface px-3 py-2 text-sm" />
      <input value={v.phone} onChange={set("phone")} placeholder="Телефон" className="rounded-lg border border-line2 bg-surface px-3 py-2 text-sm" />
      <input value={v.address} onChange={set("address")} placeholder="Адрес" className="rounded-lg border border-line2 bg-surface px-3 py-2 text-sm sm:col-span-2" />
      <input value={v.working_hours} onChange={set("working_hours")} placeholder="Часы работы" className="rounded-lg border border-line2 bg-surface px-3 py-2 text-sm" />
      <input value={v.source_url} onChange={set("source_url")} placeholder="Сайт / ссылка на прайс" className="rounded-lg border border-line2 bg-surface px-3 py-2 text-sm" />
      <div className="flex gap-2 sm:col-span-2">
        <button
          disabled={busy || !v.name.trim()}
          onClick={async () => {
            setBusy(true);
            try {
              await onSubmit(v);
            } finally {
              setBusy(false);
            }
          }}
          className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand/90 disabled:opacity-60"
        >
          {busy ? "Сохраняем…" : submitLabel}
        </button>
        <button onClick={onCancel} className="rounded-lg border border-line2 px-4 py-2 text-sm text-muted hover:text-foreground">
          Отмена
        </button>
      </div>
    </div>
  );
}

export default function ClinicsAdminPage() {
  const { session } = useAuth();
  const token = session?.access_token ?? "";

  const [items, setItems] = useState<AdminClinic[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [openOffers, setOpenOffers] = useState<number | null>(null);

  const load = useCallback(
    async (term: string) => {
      if (!token) return;
      setLoading(true);
      try {
        const r = await adminApi.clinics(token, term || undefined, 100);
        setItems(r.items);
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

  async function create(v: typeof EMPTY) {
    try {
      await adminApi.createClinic(token, v);
      setAdding(false);
      setMsg("Клиника добавлена.");
      await load(q);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function update(id: number, v: typeof EMPTY) {
    try {
      await adminApi.patchClinic(token, id, v);
      setEditing(null);
      setMsg("Сохранено.");
      await load(q);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function remove(c: AdminClinic) {
    if (!confirm(`Удалить клинику «${c.name}» и все её цены? Действие необратимо.`)) return;
    try {
      await adminApi.deleteClinic(token, c.id);
      setItems((xs) => xs.filter((x) => x.id !== c.id));
      setTotal((t) => Math.max(0, t - 1));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-line bg-surface p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-foreground">Клиники</h2>
            <p className="mt-1 text-sm text-muted">
              Добавляйте и правьте клиники и их цены вручную. Массовую загрузку прайса делает{" "}
              <Link href="/admin/import" className="text-brand hover:underline">
                мастер импорта
              </Link>
              .
            </p>
          </div>
          <button
            onClick={() => {
              setAdding((a) => !a);
              setEditing(null);
            }}
            className="rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand/90"
          >
            {adding ? "Закрыть" : "+ Клиника"}
          </button>
        </div>

        {adding && (
          <div className="mt-4 rounded-xl border border-line bg-surface2/40 p-4">
            <ClinicForm initial={EMPTY} onSubmit={create} onCancel={() => setAdding(false)} submitLabel="Добавить" />
          </div>
        )}

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
            placeholder="Поиск клиники по названию…"
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
            Всего клиник: <span className="text-brand-ink">{total.toLocaleString("ru-RU")}</span>
          </h3>
          <button onClick={() => load(q)} className="text-sm text-brand hover:underline">
            Обновить
          </button>
        </div>

        {loading ? (
          <p className="px-5 py-8 text-center text-sm text-muted">Загружаем…</p>
        ) : items.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-muted">Ничего не найдено.</p>
        ) : (
          <div className="divide-y divide-line">
            {items.map((c) => (
              <div key={c.id}>
                <div className="grid grid-cols-[1fr_auto] items-center gap-3 px-5 py-3">
                  <div className="min-w-0">
                    <span className="block truncate text-sm font-medium text-foreground">
                      {c.name}
                      {c.source_type !== "web" && (
                        <span className="ml-2 rounded bg-brand/10 px-1.5 py-0.5 text-xs font-semibold text-brand-ink">
                          {c.source_type}
                        </span>
                      )}
                    </span>
                    <span className="text-xs text-faint">
                      {c.city || "город не указан"}
                      {c.address ? ` · ${c.address}` : ""} · цен: {c.n_offers ?? 0}
                    </span>
                  </div>
                  <div className="flex shrink-0 items-center gap-2 text-xs font-semibold">
                    <button
                      onClick={() => setOpenOffers(openOffers === c.id ? null : c.id)}
                      className="rounded-lg px-2.5 py-1.5 text-brand hover:bg-surface2"
                    >
                      Цены
                    </button>
                    <Link
                      href={`/admin/import?clinic=${c.id}`}
                      className="rounded-lg px-2.5 py-1.5 text-muted hover:bg-surface2 hover:text-foreground"
                    >
                      Импорт
                    </Link>
                    <button
                      onClick={() => {
                        setEditing(editing === c.id ? null : c.id);
                        setOpenOffers(null);
                      }}
                      className="rounded-lg px-2.5 py-1.5 text-muted hover:bg-surface2 hover:text-foreground"
                    >
                      Править
                    </button>
                    <button
                      onClick={() => remove(c)}
                      className="rounded-lg px-2.5 py-1.5 text-muted hover:bg-surface2 hover:text-warn"
                    >
                      Удалить
                    </button>
                  </div>
                </div>
                {editing === c.id && (
                  <div className="border-t border-line bg-surface2/40 px-5 py-4">
                    <ClinicForm
                      initial={{
                        name: c.name,
                        city: c.city || "",
                        address: c.address || "",
                        phone: c.phone || "",
                        working_hours: c.working_hours || "",
                        source_url: c.source_url || "",
                      }}
                      onSubmit={(v) => update(c.id, v)}
                      onCancel={() => setEditing(null)}
                      submitLabel="Сохранить"
                    />
                  </div>
                )}
                {openOffers === c.id && <OffersPanel clinic={c} token={token} />}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
