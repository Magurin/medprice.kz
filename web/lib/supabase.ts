"use client";

import { createClient, SupabaseClient } from "@supabase/supabase-js";

// Публичные значения (anon-ключ защищён RLS, его можно держать на клиенте).
const url = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

// Один экземпляр на вкладку. Если env не заданы - клиент null, UI покажет подсказку.
let _client: SupabaseClient | null = null;

export const isSupabaseConfigured = Boolean(url && anon);

export function getSupabase(): SupabaseClient | null {
  if (!isSupabaseConfigured) return null;
  if (!_client) {
    _client = createClient(url, anon, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    });
  }
  return _client;
}
