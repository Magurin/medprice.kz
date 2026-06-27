"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, SubscriptionRow, tenge } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function SubscriptionsPage() {
  const { user, email, loading: authLoading } = useAuth();
  const [subs, setSubs] = useState<SubscriptionRow[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (e: string) => {
    setLoading(true);
    try {
      const r = await api.subscriptions(e);
      setSubs(r.subscriptions);
    } catch {
      setSubs([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (email) load(email);
  }, [email, load]);

  async function remove(id: number) {
    await api.unsubscribe(id);
    setSubs((s) => s.filter((x) => x.id !== id));
  }

  if (!authLoading && !user) {
    return (
      <div className="mx-auto max-w-sm px-4 py-16 text-center">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">Мои подписки</h1>
        <p className="mt-2 text-sm text-muted">Войдите, чтобы видеть свои подписки на цены.</p>
        <div className="mt-5 flex justify-center gap-2">
          <Link href="/login" className="rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand/90">
            Войти
          </Link>
          <Link href="/register" className="rounded-xl border border-line2 px-4 py-2.5 text-sm font-medium text-foreground hover:bg-surface2">
            Регистрация
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-7">
      <h1 className="text-2xl font-semibold tracking-tight text-foreground">Мои подписки</h1>
      <p className="mt-1 text-sm text-muted">
        Отслеживание цен для <b>{email}</b>.
      </p>

      {(loading || authLoading) && <div className="mt-6 h-24 animate-pulse rounded-2xl border border-line bg-surface2" />}

      {!loading && !authLoading && subs.length === 0 && (
        <div className="mt-6 rounded-2xl border border-dashed border-line2 bg-surface p-8 text-center text-sm text-muted">
          Подписок нет. Откройте услугу и нажмите «Подписаться на цену».
        </div>
      )}

      {subs.length > 0 && (
        <div className="mt-6 space-y-2">
          {subs.map((s) => {
            const up = s.delta != null && s.delta > 0;
            const down = s.delta != null && s.delta < 0;
            return (
              <div key={s.id} className="flex items-center gap-3 rounded-2xl border border-line bg-surface px-4 py-3">
                <div className="min-w-0 flex-1">
                  <Link href={`/service/${encodeURIComponent(s.code || "")}`} className="font-medium text-foreground hover:text-brand-ink">
                    {s.service}
                  </Link>
                  <div className="text-xs text-faint">
                    {s.clinic ? s.clinic : "минимум по рынку"}
                    {s.city ? ` · ${s.city}` : ""}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-semibold tabular-nums text-foreground">
                    {s.current_price != null ? tenge(s.current_price) : "-"}
                  </div>
                  {s.delta != null && s.delta !== 0 && (
                    <div className={`text-xs tabular-nums ${down ? "text-deal" : "text-warn"}`}>
                      {up ? "▲ +" : "▼ "}
                      {tenge(Math.abs(s.delta))} с подписки
                    </div>
                  )}
                  {s.delta === 0 && <div className="text-xs text-faint">без изменений</div>}
                </div>
                <button
                  onClick={() => remove(s.id)}
                  className="shrink-0 rounded-lg border border-line2 px-2.5 py-1.5 text-xs text-muted hover:border-warn hover:text-warn"
                >
                  Отписаться
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
