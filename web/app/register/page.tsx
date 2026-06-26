"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import GoogleButton from "@/components/GoogleButton";
import PasswordField, { isPasswordStrong } from "@/components/PasswordField";
import AuthShell from "@/components/auth/AuthShell";
import AuthField from "@/components/auth/AuthField";

export default function RegisterPage() {
  const { signUpEmail, configured } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [msg, setMsg] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (username.trim().length < 2) return fail("Логин слишком короткий");
    if (!email.includes("@")) return fail("Введите корректную почту");
    if (!isPasswordStrong(pw))
      return fail("Пароль: минимум 8 символов, цифры, заглавные и строчные буквы");
    if (pw !== pw2) return fail("Пароли не совпадают");
    setState("loading");
    try {
      await signUpEmail(username.trim(), email.trim(), pw);
      setState("done");
      setMsg("Аккаунт создан. Если включено подтверждение почты — проверьте письмо, иначе можно войти.");
      setTimeout(() => router.push("/login"), 1800);
    } catch (err) {
      fail(err instanceof Error ? err.message : String(err));
    }
  }
  function fail(m: string) {
    setState("error");
    setMsg(m);
  }

  return (
    <AuthShell title="Создать аккаунт" subtitle="Подписывайтесь на изменения цен в клиниках.">
      {!configured && (
        <div className="mb-4 rounded-xl bg-warn-tint/60 px-4 py-3 text-sm text-warn">
          Авторизация ещё не настроена: добавьте ключи Supabase в окружение фронтенда.
        </div>
      )}

      {state === "done" ? (
        <div className="rounded-2xl border border-line bg-deal-tint/50 p-5 text-sm text-foreground">{msg}</div>
      ) : (
        <>
          <form onSubmit={submit} className="space-y-3.5">
            <AuthField label="Логин" value={username} onChange={setUsername} placeholder="ivan" autoComplete="username" />
            <AuthField label="Почта" type="email" value={email} onChange={setEmail} placeholder="you@example.com" autoComplete="email" />
            <PasswordField label="Пароль" value={pw} onChange={setPw} placeholder="••••••••" autoComplete="new-password" showStrength />
            <PasswordField label="Повторите пароль" value={pw2} onChange={setPw2} placeholder="••••••••" autoComplete="new-password" />

            {state === "error" && <p className="text-sm text-warn">{msg}</p>}

            <button
              type="submit"
              disabled={state === "loading"}
              className="w-full rounded-xl bg-brand py-3 text-sm font-semibold text-white transition-colors hover:bg-brand/90 disabled:opacity-60"
            >
              {state === "loading" ? "Создаём…" : "Зарегистрироваться"}
            </button>
          </form>

          <div className="my-5 flex items-center gap-3 text-xs text-faint">
            <span className="h-px flex-1 bg-line" /> или <span className="h-px flex-1 bg-line" />
          </div>
          <GoogleButton label="Зарегистрироваться с помощью Google" />

          <div className="my-5 flex items-center gap-3 text-xs text-faint">
            <span className="h-px flex-1 bg-line" /> Уже есть аккаунт? <span className="h-px flex-1 bg-line" />
          </div>
          <Link
            href="/login"
            className="block w-full rounded-xl border border-line2 py-3 text-center text-sm font-semibold text-foreground transition-colors hover:border-brand hover:text-brand-ink"
          >
            Войти
          </Link>
        </>
      )}
    </AuthShell>
  );
}
