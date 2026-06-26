"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CityRow } from "@/lib/api";

const ALL = "__all__";

// Кастомный выпадающий список городов в стиле сайта:
// поиск по названию, счётчики клиник, скролл и навигация с клавиатуры.
export default function CityPicker({
  value,
  cities,
  onChange,
  triggerClassName = "",
  size = "md",
  placeholder = "Все города",
  align = "left",
}: {
  value: string;
  cities: CityRow[];
  onChange: (v: string) => void;
  /** доп. классы для кнопки-триггера (рамка/фон/высота под контекст) */
  triggerClassName?: string;
  size?: "md" | "sm";
  placeholder?: string;
  align?: "left" | "right";
}) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // [{ value:"", label:"Все города" }, ...города]
  const options = useMemo(() => {
    const f = filter.trim().toLowerCase();
    const list = cities.filter((c) => !f || c.city.toLowerCase().includes(f));
    const head = !f || placeholder.toLowerCase().includes(f) ? [{ city: "", clinics: 0 }] : [];
    return [...head, ...list];
  }, [cities, filter, placeholder]);

  const label = value || placeholder;

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  useEffect(() => {
    if (open) {
      setFilter("");
      setActive(0);
      // фокус на поле поиска после открытия
      const t = setTimeout(() => inputRef.current?.focus(), 0);
      return () => clearTimeout(t);
    }
  }, [open]);

  // держим активный пункт в зоне видимости
  useEffect(() => {
    const el = listRef.current?.children[active] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const pick = (v: string) => {
    onChange(v);
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, options.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const opt = options[active];
      if (opt) pick(opt.city);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const h = size === "sm" ? "h-11" : "h-12";

  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={
          triggerClassName ||
          `flex ${h} w-full cursor-pointer items-center gap-2 rounded-xl border border-line2 bg-surface pl-3.5 pr-3 text-sm text-foreground outline-none transition-colors hover:border-brand/50 focus:border-brand`
        }
      >
        <svg className="h-[18px] w-[18px] shrink-0 text-faint" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 21s-7-5.7-7-11a7 7 0 1 1 14 0c0 5.3-7 11-7 11Z" />
          <circle cx="12" cy="10" r="2.5" />
        </svg>
        <span className={`flex-1 truncate text-left ${value ? "text-foreground" : "text-muted"}`}>{label}</span>
        <svg
          className={`h-4 w-4 shrink-0 text-faint transition-transform ${open ? "rotate-180" : ""}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="m6 9 6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div
          className={`absolute top-full z-50 mt-2 w-[min(280px,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-line bg-surface shadow-[0_20px_50px_-20px_rgba(12,24,34,0.35)] ${
            align === "right" ? "right-0" : "left-0"
          }`}
        >
          <div className="border-b border-line p-2">
            <input
              ref={inputRef}
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value);
                setActive(0);
              }}
              onKeyDown={onKeyDown}
              placeholder="Поиск города…"
              className="h-9 w-full rounded-lg border border-line2 bg-surface2 px-3 text-sm text-foreground outline-none placeholder:text-faint focus:border-brand"
            />
          </div>

          <div ref={listRef} className="max-h-72 overflow-y-auto py-1" role="listbox">
            {options.length === 0 && (
              <div className="px-3.5 py-3 text-sm text-faint">Ничего не нашлось</div>
            )}
            {options.map((c, i) => {
              const selected = c.city === value;
              return (
                <button
                  key={c.city || ALL}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  onMouseEnter={() => setActive(i)}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => pick(c.city)}
                  className={`flex w-full items-center justify-between gap-3 px-3.5 py-2 text-left text-sm transition-colors ${
                    i === active ? "bg-brand-tint" : ""
                  } ${selected ? "font-semibold text-brand-ink" : "text-foreground"}`}
                >
                  <span className="truncate">{c.city || placeholder}</span>
                  {c.city ? (
                    <span className="shrink-0 text-xs tabular-nums text-faint">{c.clinics}</span>
                  ) : null}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
