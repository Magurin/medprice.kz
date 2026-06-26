"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { getSupabase, isSupabaseConfigured } from "@/lib/supabase";

interface AuthCtx {
  user: User | null;
  session: Session | null;
  loading: boolean;
  configured: boolean;
  username: string | null;
  email: string | null;
  role: string | null; // строка из public.staff: 'admin' | 'moderator' | null (обычный юзер)
  isStaff: boolean; // есть запись в staff → доступ в /admin
  signUpEmail: (username: string, email: string, password: string) => Promise<void>;
  signInLogin: (login: string, password: string) => Promise<void>;
  signInGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [role, setRole] = useState<string | null>(null);

  // Роль читаем из public.staff. RLS (staff_self_read) отдаёт строку только владельцу,
  // поэтому обычный юзер получит null — это и есть «не сотрудник».
  async function loadRole(s: Session | null) {
    const sb = getSupabase();
    if (!sb || !s?.user) {
      setRole(null);
      return;
    }
    const { data } = await sb
      .from("staff")
      .select("role")
      .eq("user_id", s.user.id)
      .maybeSingle();
    setRole((data?.role as string) ?? null);
  }

  useEffect(() => {
    const sb = getSupabase();
    if (!sb) {
      setLoading(false);
      return;
    }
    sb.auth.getSession().then(async ({ data }) => {
      setSession(data.session);
      await loadRole(data.session);
      setLoading(false);
    });
    const { data: sub } = sb.auth.onAuthStateChange((_e, s) => {
      setSession(s);
      loadRole(s);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  async function signUpEmail(username: string, email: string, password: string) {
    const sb = getSupabase();
    if (!sb) throw new Error("Авторизация не настроена (нет ключей Supabase).");
    const { error } = await sb.auth.signUp({
      email,
      password,
      options: {
        data: { username },
        emailRedirectTo: typeof window !== "undefined" ? window.location.origin : undefined,
      },
    });
    if (error) throw new Error(error.message);
  }

  async function signInLogin(login: string, password: string) {
    const sb = getSupabase();
    if (!sb) throw new Error("Авторизация не настроена (нет ключей Supabase).");
    let email = login.trim();
    if (!email.includes("@")) {
      // вход по логину: резолвим email через RPC email_for_login
      const { data, error } = await sb.rpc("email_for_login", { login: email });
      if (error) throw new Error("Не удалось войти по логину. Попробуйте email.");
      if (!data) throw new Error("Пользователь с таким логином не найден.");
      email = data as string;
    }
    const { error } = await sb.auth.signInWithPassword({ email, password });
    if (error) throw new Error(error.message);
  }

  async function signInGoogle() {
    const sb = getSupabase();
    if (!sb) throw new Error("Авторизация не настроена (нет ключей Supabase).");
    const { error } = await sb.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: typeof window !== "undefined" ? window.location.origin : undefined },
    });
    if (error) throw new Error(error.message);
  }

  async function signOut() {
    const sb = getSupabase();
    await sb?.auth.signOut();
    setSession(null);
    setRole(null);
  }

  const user = session?.user ?? null;
  const value: AuthCtx = {
    user,
    session,
    loading,
    configured: isSupabaseConfigured,
    username: (user?.user_metadata?.username as string) ?? null,
    email: user?.email ?? null,
    role,
    isStaff: role !== null,
    signUpEmail,
    signInLogin,
    signInGoogle,
    signOut,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth должен использоваться внутри <AuthProvider>");
  return ctx;
}
