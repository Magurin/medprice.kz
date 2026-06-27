// Типизированный клиент к FastAPI-бэкенду MedPrice KZ.
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://127.0.0.1:8077";

export interface Stats {
  cities: number;
  clinics: number;
  services: number;
  comparable_services: number;
  offers: number;
  priced_offers: number;
  curated_services: number;
}

export interface CityRow {
  city: string;
  clinics: number;
}

export interface ClinicRow {
  id: number;
  name: string;
  city: string | null;
  address: string | null;
  host: string;
  source_url: string | null;
  source_type: string;
  lat: number | null;
  lng: number | null;
  rating?: number | null;
  reviews_count?: number | null;
  twogis_url?: string | null;
}

export interface ClinicService {
  code: string;
  service: string;
  category: string | null;
  price: number;
  raw_name: string;
}

export interface ClinicCard {
  id: number;
  name: string;
  city: string | null;
  address: string | null;
  phone: string | null;
  working_hours: string | null;
  source_url: string | null;
  source_type: string | null;
  lat: number | null;
  lng: number | null;
  rating?: number | null;
  reviews_count?: number | null;
  twogis_url?: string | null;
  services_count: number;
  services: ClinicService[];
}

export interface CategoryRow {
  category: string;
  services: number;
}

export interface ServiceRow {
  code: string;
  name: string;
  category: string | null;
  is_curated: boolean;
  clinics: number;
  offers: number;
}

export interface SearchResult {
  code: string;
  name: string;
  category: string | null;
  is_curated: boolean;
  clinics: number;
  min_price: number;
  max_price: number;
  avg_price: number;
}

export interface SearchResponse {
  query: string;
  city: string | null;
  results: SearchResult[];
}

export interface Offer {
  clinic: string;
  clinic_id?: number | null;
  city: string | null;
  address: string | null;
  working_hours?: string | null;
  raw_name: string;
  price: number;
  is_from: boolean;
  source_url: string | null;
  rating?: number | null;
  reviews_count?: number | null;
  twogis_url?: string | null;
  lat?: number | null;
  lng?: number | null;
  parsed_at?: string | null;
  source_file?: string | null;
  source_type?: string | null;
}

export interface CompareStats {
  count: number;
  min: number;
  max: number;
  avg: number;
  median: number;
  savings: number;
  savings_pct: number;
}

export interface Compare {
  code: string;
  name: string;
  category: string | null;
  is_curated: boolean;
  city: string | null;
  last_updated?: string | null;
  stats: CompareStats;
  offers: Offer[];
}

export interface MatchResult {
  input: string;
  input_price: number | null;
  matched: { code: string; name: string; method: string; score: number } | null;
  market?: { clinics: number; min: number; max: number; avg: number };
  verdict?: string;
  vs_min_pct?: number;
}

export interface HistoryPoint {
  date: string;
  year: number;
  price: number;
}
export interface HistorySeries {
  clinic_id: number;
  clinic: string;
  points: HistoryPoint[];
}
export interface HistoryResponse {
  code: string;
  name: string;
  years: number[];
  series: HistorySeries[];
}

export interface BasketClinic {
  clinic_id: number;
  clinic: string;
  city: string | null;
  address: string | null;
  lat: number | null;
  lng: number | null;
  source_url: string | null;
  rating?: number | null;
  reviews_count?: number | null;
  twogis_url?: string | null;
  prices: Record<string, number>;
  covered: number;
  total: number;
  is_complete: boolean;
}
export interface BasketResponse {
  services: { code: string; name: string; category: string | null }[];
  clinics: BasketClinic[];
  cheapest_complete: number | null;
  city: string | null;
}

export interface SubscriptionRow {
  id: number;
  email: string;
  code: string | null;
  service: string | null;
  clinic_id: number | null;
  clinic: string | null;
  city: string | null;
  last_price: number | null;
  current_price: number | null;
  delta: number | null;
  changed: boolean;
  created_at: string | null;
}

// Прайсы в БД обновляются раз в сутки (cron 03:00 UTC, см. .github/workflows).
// Поэтому каталожные данные кэшируем на сутки и метим тегом "catalog" -
// фоновое обновление чистит кэш точечно через /api/revalidate.
const CATALOG_TTL = 60 * 60 * 24; // 24 часа
const CATALOG_TAG = "catalog";

// Каталожные (одинаковые для всех) GET-запросы - кэшируем; пользовательские - нет.
async function get<T>(path: string, opts?: { cache?: boolean }): Promise<T> {
  const init: RequestInit =
    opts?.cache === false
      ? { cache: "no-store" }
      : { next: { revalidate: CATALOG_TTL, tags: [CATALOG_TAG] } };
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let msg = `API ${res.status}`;
    try {
      const j = await res.json();
      if (j.detail) msg = j.detail;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

const qs = (params: Record<string, string | number | undefined>) => {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "" && v !== null) u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
};

export const api = {
  stats: () => get<Stats>("/api/stats"),
  cities: () => get<CityRow[]>("/api/cities"),
  clinics: (p: { city?: string; q?: string; with_coords?: boolean; min_rating?: number; limit?: number }) =>
    get<ClinicRow[]>(`/api/clinics${qs({ ...p, with_coords: p.with_coords ? 1 : undefined })}`),
  clinicsCount: (p: { city?: string; q?: string; with_coords?: boolean; min_rating?: number }) =>
    get<{ count: number }>(`/api/clinics/count${qs({ ...p, with_coords: p.with_coords ? 1 : undefined })}`),
  clinicCard: (id: number) => get<ClinicCard>(`/api/clinics/${id}`),
  categories: () => get<CategoryRow[]>("/api/categories"),
  services: (p: { q?: string; category?: string; min_clinics?: number; limit?: number }) =>
    get<ServiceRow[]>(`/api/services${qs(p)}`),
  search: (q: string, city?: string) =>
    get<SearchResponse>(`/api/search${qs({ q, city })}`),
  compare: (code: string, city?: string) =>
    get<Compare>(`/api/services/${encodeURIComponent(code)}/compare${qs({ city })}`),
  history: (code: string) =>
    get<HistoryResponse>(`/api/services/${encodeURIComponent(code)}/history`),
  compareBasket: (codes: string[], city?: string, source?: string) =>
    send<BasketResponse>("POST", "/api/compare/basket", { codes, city, source }),
  subscribe: (p: { email: string; code: string; clinic_id?: number; city?: string }) =>
    send<{ status: string; subscription: SubscriptionRow }>("POST", "/api/subscriptions", p),
  subscriptions: (email: string) =>
    get<{ email: string; subscriptions: SubscriptionRow[] }>(
      `/api/subscriptions${qs({ email })}`,
      { cache: false } // персональные данные - не кэшируем
    ),
  unsubscribe: (id: number) =>
    send<{ status: string; id: number }>("DELETE", `/api/subscriptions/${id}`),
  matchPrices: async (items: { name: string; price?: number }[], city?: string) => {
    const res = await fetch(`${API_BASE}/api/ingest/match`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items, city }),
    });
    if (!res.ok) throw new Error(`API ${res.status}`);
    return res.json() as Promise<{ count: number; results: MatchResult[] }>;
  },
};

// ---------- админ-API (только staff; требует Supabase access token) ----------
export interface ParseRunRow {
  id: number;
  source_kind: string;
  trigger: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  duration_sec: number | null;
  sources_total: number;
  sources_ok: number;
  sources_failed: number;
  rows_raw: number;
  rows_new: number;
  rows_dup: number;
  note: string | null;
}
export interface ParseLogLine {
  ts: string | null;
  level: string; // info | warn | error
  source: string | null;
  stage: string | null;
  message: string | null;
}
export interface ParseRunDetail extends ParseRunRow {
  errors: { source: string; stage: string; error: string; created_at: string | null }[];
  logs: ParseLogLine[];
}

export interface ParseScheduleRow {
  enabled: boolean;
  hour: number; // UTC
  minute: number; // UTC
  time_utc: string;
  time_almaty: string;
  kind: string;
  run_limit: number;
  step_minutes: number;
  updated_at: string | null;
  updated_by: string | null;
}

async function authReq<T>(method: string, path: string, token: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let msg = `API ${res.status}`;
    try {
      const j = await res.json();
      if (j.detail) msg = j.detail;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

export interface UnmatchedGroup {
  raw_name: string;
  count: number;
  min_price: number | null;
  max_price: number | null;
}

export const adminApi = {
  me: (token: string) => authReq<{ user_id: string; role: string }>("GET", "/api/admin/me", token),
  runs: (token: string) => authReq<ParseRunRow[]>("GET", "/api/admin/parse/runs", token),
  run: (token: string, id: number) =>
    authReq<ParseRunDetail>("GET", `/api/admin/parse/runs/${id}`, token),
  trigger: (token: string, body: { kind: string; limit?: number; hosts?: string }) =>
    authReq<{ status: string; run: ParseRunRow }>("POST", "/api/admin/parse/run", token, body),

  // расписание ежедневного парсинга (ТЗ §3.1: запуск по cron, время — из UI)
  schedule: (token: string) =>
    authReq<ParseScheduleRow>("GET", "/api/admin/parse/schedule", token),
  saveSchedule: (
    token: string,
    body: { enabled?: boolean; hour?: number; minute?: number; kind?: string; run_limit?: number }
  ) => authReq<ParseScheduleRow>("PUT", "/api/admin/parse/schedule", token, body),

  // очередь ручной разметки (ТЗ §3.2)
  unmatched: (token: string, q?: string) =>
    authReq<{ total: number; items: UnmatchedGroup[] }>(
      "GET",
      `/api/admin/unmatched${qs({ q })}`,
      token
    ),
  assignMatch: (token: string, raw_name: string, service_code: string) =>
    authReq<{ status: string; service: string; rows_closed: number; offers_created: number }>(
      "POST",
      "/api/admin/unmatched/assign",
      token,
      { raw_name, service_code }
    ),
  skipMatch: (token: string, raw_name: string) =>
    authReq<{ status: string; rows_closed: number }>(
      "POST",
      "/api/admin/unmatched/skip",
      token,
      { raw_name }
    ),

  // источники парсинга (ТЗ §3.1)
  sources: (token: string) => authReq<ParseSourceRow[]>("GET", "/api/admin/sources", token),
  addSource: (token: string, body: { value: string; label?: string; note?: string }) =>
    authReq<ParseSourceRow>("POST", "/api/admin/sources", token, body),
  patchSource: (
    token: string,
    id: number,
    body: { enabled?: boolean; label?: string; note?: string }
  ) => authReq<ParseSourceRow>("PATCH", `/api/admin/sources/${id}`, token, body),
  deleteSource: (token: string, id: number) =>
    authReq<{ status: string; id: number }>("DELETE", `/api/admin/sources/${id}`, token),

  // --- ведение каталога модераторами: клиники / услуги / цены ---
  clinics: (token: string, q?: string, limit = 50, offset = 0) =>
    authReq<{ total: number; limit: number; offset: number; items: AdminClinic[] }>(
      "GET",
      `/api/admin/clinics${qs({ q, limit, offset })}`,
      token
    ),
  createClinic: (token: string, body: ClinicInput) =>
    authReq<AdminClinic>("POST", "/api/admin/clinics", token, body),
  patchClinic: (token: string, id: number, body: Partial<ClinicInput>) =>
    authReq<AdminClinic>("PATCH", `/api/admin/clinics/${id}`, token, body),
  deleteClinic: (token: string, id: number) =>
    authReq<{ status: string; id: number }>("DELETE", `/api/admin/clinics/${id}`, token),

  createService: (token: string, body: { name: string; category?: string; code?: string }) =>
    authReq<{ id: number; code: string; name: string; category: string | null }>(
      "POST",
      "/api/admin/services",
      token,
      body
    ),
  patchService: (token: string, id: number, body: { name?: string; category?: string }) =>
    authReq<{ id: number; code: string; name: string; category: string | null }>(
      "PATCH",
      `/api/admin/services/${id}`,
      token,
      body
    ),

  clinicOffers: (token: string, clinicId: number) =>
    authReq<{ clinic_id: number; clinic: string; offers: AdminOffer[] }>(
      "GET",
      `/api/admin/clinics/${clinicId}/offers`,
      token
    ),
  createOffer: (
    token: string,
    body: {
      clinic_id: number;
      raw_name: string;
      price?: number | null;
      service_code?: string;
      service_name?: string;
      category?: string;
    }
  ) => authReq<AdminOffer>("POST", "/api/admin/offers", token, body),
  patchOffer: (
    token: string,
    id: number,
    body: { raw_name?: string; price?: number | null; on_request?: boolean; service_code?: string }
  ) => authReq<AdminOffer>("PATCH", `/api/admin/offers/${id}`, token, body),
  deleteOffer: (token: string, id: number) =>
    authReq<{ status: string; id: number }>("DELETE", `/api/admin/offers/${id}`, token),

  // --- импорт прайс-листов (HTML / PDF / DOCX / Excel) ---
  importFile: async (token: string, file: File): Promise<ImportPreview> => {
    // тело запроса = байты файла; имя кладём в query (без python-multipart на бэке)
    const res = await fetch(`${API_BASE}/api/admin/import/parse${qs({ filename: file.name })}`, {
      method: "POST",
      cache: "no-store",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/octet-stream",
      },
      body: file,
    });
    if (!res.ok) {
      let msg = `API ${res.status}`;
      try {
        const j = await res.json();
        if (j.detail) msg = j.detail;
      } catch {}
      throw new Error(msg);
    }
    return res.json();
  },
  importUrl: (token: string, url: string) =>
    authReq<ImportPreview>("POST", "/api/admin/import/url", token, { url }),
  importCommit: (
    token: string,
    body: { clinic_id: number; source?: string; replace?: boolean; rows: ImportCommitRow[] }
  ) =>
    authReq<{ status: string; clinic: string; offers_created: number; services_created: number }>(
      "POST",
      "/api/admin/import/commit",
      token,
      body
    ),
};

export interface AdminClinic {
  id: number;
  host: string;
  name: string;
  city: string | null;
  city_id: number | null;
  address: string | null;
  phone: string | null;
  working_hours: string | null;
  source_url: string | null;
  source_type: string | null;
  lat: number | null;
  lng: number | null;
  rating: number | null;
  reviews_count: number | null;
  n_offers: number | null;
}

export interface ClinicInput {
  name: string;
  city?: string;
  address?: string;
  phone?: string;
  working_hours?: string;
  source_url?: string;
  host?: string;
  lat?: number | null;
  lng?: number | null;
}

export interface AdminOffer {
  id: number;
  raw_name: string;
  price: number | null;
  on_request: boolean;
  is_from: boolean;
  source_type: string | null;
  match_method: string | null;
  service_code: string | null;
  service_name: string | null;
  category: string | null;
}

export interface ImportMatch {
  code: string;
  name: string;
  category: string | null;
  method: string;
  score: number;
}
export interface ImportPreviewRow {
  raw_name: string;
  price: number | null;
  unit: string | null;
  section: string | null;
  code: string | null;
  match: ImportMatch | null;
  known_skip: boolean;
}
export interface ImportPreview {
  source: string;
  total: number;
  auto_matched: number;
  rows: ImportPreviewRow[];
}
export interface ImportCommitRow {
  raw_name: string;
  price?: number | null;
  service_code?: string;
  service_name?: string;
  category?: string;
  create_new?: boolean;
  skip?: boolean;
}

export interface ParseSourceRow {
  id: number;
  kind: string; // frontier | host
  value: string;
  label: string | null;
  enabled: boolean;
  note: string | null;
  last_run_at: string | null;
  last_count: number | null;
  frontier_size: number | null;
}

export const tenge = (n: number) => `${n.toLocaleString("ru-RU")} ₸`;

// Цена покороче для тесных мест: 1 200 ₸, 40 000 ₸
export const tengeShort = (n: number) => `${n.toLocaleString("ru-RU")} ₸`;

// Часть клиник в данных названы slug-ами вида "detskaja-bolynica-karaganda".
// Приводим их к читабельному виду; уже нормальные названия не трогаем.
export const prettyClinic = (name: string): string => {
  if (/^[a-z0-9][a-z0-9-]*$/.test(name)) {
    return name
      .split("-")
      .filter(Boolean)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
  }
  return name;
};

export const cityLabel = (city: string | null | undefined) =>
  !city || city === "Не указан" ? "город не указан" : city;

// Диплинк в 2ГИС: построить маршрут до точки клиники (без API-ключа).
// Формат routeSearch: /routeSearch/rsType/<пеший|авто>/to/<lon>,<lat>
export const twoGisRoute = (
  lat: number | null | undefined,
  lng: number | null | undefined,
  mode: "car" | "pedestrian" = "car"
): string | null => {
  if (lat == null || lng == null) return null;
  return `https://2gis.kz/routeSearch/rsType/${mode}/to/${lng},${lat}`;
};
