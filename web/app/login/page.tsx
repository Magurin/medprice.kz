"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import GoogleButton from "@/components/GoogleButton";
import PasswordField from "@/components/PasswordField";
import AuthShell from "@/components/auth/AuthShell";
import AuthField from "@/components/auth/AuthField";

export default function LoginPage() {
  const { signInLogin, configured } = useAuth();
  const router = useRouter();
  const [login, setLogin] = useState("");
  const [pw, setPw] = useState("");
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [msg, setMsg] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!login.trim() || !pw) {
      setState("error");
      setMsg("Введите логин/почту и пароль");
      return;
    }
    setState("loading");
    try {
      await signInLogin(login, pw);
      router.push("/subscriptions");
    } catch (err) {
      setState("error");
      setMsg(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <AuthShell title="Вход в аккаунт" subtitle="Управляйте подписками на цены.">
      {!configured && (
        <div className="mb-4 rounded-xl bg-warn-tint/60 px-4 py-3 text-sm text-warn">
          Авторизация ещё не настроена: добавьте ключи Supabase в окружение фронтенда.
        </div>
      )}

      <form onSubmit={submit} className="space-y-3.5">
        <AuthField
          label="Логин или почта"
          value={login}
          onChange={setLogin}
          placeholder="ivan или you@example.com"
          autoComplete="username"
        />
        <PasswordField label="Пароль" value={pw} onChange={setPw} placeholder="••••••••" autoComplete="current-password" />

        {state === "error" && <p className="text-sm text-warn">{msg}</p>}

        <button
          type="submit"
          disabled={state === "loading"}
          className="w-full rounded-xl bg-brand py-3 text-sm font-semibold text-white transition-colors hover:bg-brand/90 disabled:opacity-60"
        >
          {state === "loading" ? "Входим…" : "Войти"}
        </button>
      </form>

      <div className="my-5 flex items-center gap-3 text-xs text-faint">
        <span className="h-px flex-1 bg-line" /> или <span className="h-px flex-1 bg-line" />
      </div>
      <GoogleButton label="Войти с помощью Google" />

      <div className="my-5 flex items-center gap-3 text-xs text-faint">
        <span className="h-px flex-1 bg-line" /> Нет аккаунта? <span className="h-px flex-1 bg-line" />
      </div>
      <Link
        href="/register"
        className="block w-full rounded-xl border border-line2 py-3 text-center text-sm font-semibold text-foreground transition-colors hover:border-brand hover:text-brand-ink"
      >
        Зарегистрироваться
      </Link>
    </AuthShell>
  );
}
