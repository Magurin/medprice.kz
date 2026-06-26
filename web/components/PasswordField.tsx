"use client";

import { useState } from "react";

// ── правила пароля (общие для поля и для submit) ───────────────────────────
export interface PasswordChecks {
  minLength: boolean; // ≥ 8 символов
  digit: boolean;     // есть цифра
  upper: boolean;     // есть заглавная буква
  lower: boolean;     // есть строчная буква
}

export const MIN_PASSWORD = 8;

export function checkPassword(pw: string): PasswordChecks {
  return {
    minLength: pw.length >= MIN_PASSWORD,
    digit: /\d/.test(pw),
    upper: /[A-ZА-ЯЁ]/.test(pw),
    lower: /[a-zа-яё]/.test(pw),
  };
}

export function isPasswordStrong(pw: string): boolean {
  const c = checkPassword(pw);
  return c.minLength && c.digit && c.upper && c.lower;
}

function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}

// ── компонент поля ─────────────────────────────────────────────────────────
export default function PasswordField({
  label,
  value,
  onChange,
  placeholder,
  autoComplete = "new-password",
  showStrength = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  autoComplete?: string;
  showStrength?: boolean;
}) {
  const [show, setShow] = useState(false);

  const c = checkPassword(value);
  const score = [c.minLength, c.digit, c.upper, c.lower].filter(Boolean).length;
  const strong = score === 4;
  const touched = value.length > 0;

  // рамка: нейтральная (пусто) → красная (есть, но слабый) → зелёная (надёжный)
  const border = !touched
    ? "border-line focus-within:border-brand focus-within:bg-surface"
    : strong
      ? "border-deal"
      : "border-warn";

  // подсказка под полем
  let hint = "Минимум 8 символов: цифры, заглавные и строчные буквы.";
  let hintTone = "text-faint";
  if (touched) {
    if (!c.minLength) {
      const left = MIN_PASSWORD - value.length;
      hint = `Введите ещё ${left} ${plural(left, "символ", "символа", "символов")}. Пароль должен содержать цифры, заглавные и строчные буквы.`;
      hintTone = "text-warn";
    } else if (!strong) {
      hint = "Пароль должен содержать цифры, заглавные и строчные буквы.";
      hintTone = "text-warn";
    } else {
      hint = "Надёжный пароль";
      hintTone = "text-deal";
    }
  }

  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-muted">{label}</span>

      <div
        className={`flex items-center rounded-xl border bg-background pr-1.5 transition-colors ${border}`}
      >
        <input
          type={show ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          autoComplete={autoComplete}
          className="w-full bg-transparent px-3.5 py-2.5 text-sm text-foreground outline-none placeholder:text-faint"
        />
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          aria-label={show ? "Скрыть пароль" : "Показать пароль"}
          aria-pressed={show}
          className="shrink-0 rounded-lg p-1.5 text-faint transition-colors hover:text-muted"
        >
          {show ? <EyeOff /> : <Eye />}
        </button>
      </div>

      {showStrength && (
        <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-line">
          <div
            className={`h-full rounded-full transition-all duration-200 ${strong ? "bg-deal" : "bg-warn"}`}
            style={{ width: `${touched ? (score / 4) * 100 : 0}%` }}
          />
        </div>
      )}

      {showStrength && <p className={`mt-1.5 text-xs ${hintTone}`}>{hint}</p>}
    </label>
  );
}

function Eye() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeOff() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 3l18 18" />
      <path d="M10.6 10.6a3 3 0 0 0 4.2 4.2" />
      <path d="M9.9 4.2A10.9 10.9 0 0 1 12 4c6.5 0 10 7 10 7a18 18 0 0 1-3.2 4.1M6.6 6.6A18 18 0 0 0 2 11s3.5 7 10 7a10.9 10.9 0 0 0 4-.8" />
    </svg>
  );
}
