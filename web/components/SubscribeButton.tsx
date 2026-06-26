"use client";

import { useState } from "react";
import Link from "next/link";
import { api, tenge } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function SubscribeButton({
  code,
  city,
  clinicId,
  clinicName,
  label = "Подписаться на цену",
}: {
  code: string;
  city?: string;
  clinicId?: number;
  clinicName?: string;
  label?: string;
}) {
  const { user, email } = useAuth();
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [msg, setMsg] = useState("");

  async function submit() {
    if (!email) return;
    setState("loading");
    try {
      const r = await api.subscribe({ email, code, city, clinic_id: clinicId });
      const cur = r.subscription.current_price;
      setState("done");
      setMsg(
        r.status === "exists"
          ? "Вы уже подписаны на эту услугу."
          : `Готово! Текущая цена${cur != null ? ` — ${tenge(cur)}` : ""}. Уведомим на ${email} при изменении.`
      );
    } catch (e) {
      setState("error");
      setMsg(String(e instanceof Error ? e.message : e));
    }
  }

  return (
    <>
      <button
        onClick={() => {
          setOpen(true);
          setState("idle");
          setMsg("");
        }}
        className="inline-flex items-center gap-1.5 rounded-xl border border-brand/40 bg-brand-tint px-3 py-2 text-sm font-medium text-brand-ink transition-colors hover:bg-brand/10"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {label}
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-sm rounded-2xl border border-line bg-surface p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold text-foreground">Подписка на изменение цены</h3>

            {!user ? (
              <>
                <p className="mt-1 text-sm text-muted">
                  Войдите в аккаунт, чтобы подписаться — уведомления приходят на вашу почту.
                </p>
                <div className="mt-4 flex gap-2">
                  <Link
                    href="/login"
                    className="flex-1 rounded-xl bg-brand py-2.5 text-center text-sm font-semibold text-white hover:bg-brand/90"
                  >
                    Войти
                  </Link>
                  <Link
                    href="/register"
                    className="flex-1 rounded-xl border border-line2 py-2.5 text-center text-sm font-medium text-foreground hover:bg-surface2"
                  >
                    Регистрация
                  </Link>
                </div>
              </>
            ) : state === "done" ? (
              <div className="mt-4 rounded-xl bg-deal-tint/60 px-4 py-3 text-sm text-foreground">{msg}</div>
            ) : (
              <>
                <p className="mt-1 text-sm text-muted">
                  {clinicName ? <>Клиника <b>{clinicName}</b>. </> : null}
                  Уведомим на <b>{email}</b>, когда цена изменится.
                </p>
                {state === "error" && <p className="mt-3 text-sm text-warn">{msg}</p>}
                <button
                  onClick={submit}
                  disabled={state === "loading"}
                  className="mt-4 w-full rounded-xl bg-brand py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand/90 disabled:opacity-60"
                >
                  {state === "loading" ? "Подписываем…" : "Подписаться"}
                </button>
              </>
            )}

            <div className="mt-3 flex justify-between text-xs text-faint">
              <Link href="/subscriptions" className="hover:text-brand-ink">Мои подписки</Link>
              <button onClick={() => setOpen(false)} className="hover:text-foreground">Закрыть</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
