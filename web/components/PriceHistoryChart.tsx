"use client";

import { useMemo, useState } from "react";
import { HistoryResponse, tenge } from "@/lib/api";

// Палитра линий по клиникам.
const COLORS = ["#0d9488", "#2563eb", "#db2777", "#ea580c", "#7c3aed", "#0891b2", "#65a30d", "#dc2626"];

const W = 640;
const H = 240;
const PAD = { top: 16, right: 16, bottom: 28, left: 56 };

export default function PriceHistoryChart({ data }: { data: HistoryResponse }) {
  const [hidden, setHidden] = useState<Set<number>>(new Set());

  const model = useMemo(() => {
    const years = data.years;
    if (years.length === 0) return null;
    const allPrices = data.series.flatMap((s) => s.points.map((p) => p.price));
    if (allPrices.length === 0) return null;
    const minP = Math.min(...allPrices);
    const maxP = Math.max(...allPrices);
    const span = maxP - minP || maxP || 1;
    // отступ диапазона, чтобы линии не липли к краям
    const lo = Math.max(0, minP - span * 0.15);
    const hi = maxP + span * 0.15;

    const minYear = Math.min(...years);
    const maxYear = Math.max(...years);
    const yearSpan = maxYear - minYear || 1;

    const x = (year: number) =>
      PAD.left + ((year - minYear) / yearSpan) * (W - PAD.left - PAD.right);
    const y = (price: number) =>
      PAD.top + (1 - (price - lo) / (hi - lo)) * (H - PAD.top - PAD.bottom);

    return { years, minYear, maxYear, lo, hi, x, y };
  }, [data]);

  if (!model) return null;

  const yTicks = 4;
  const ticks = Array.from({ length: yTicks + 1 }, (_, i) =>
    Math.round(model.lo + ((model.hi - model.lo) * i) / yTicks)
  );

  const toggle = (id: number) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="График динамики цен">
        {/* сетка + подписи Y */}
        {ticks.map((t, i) => {
          const yy = model.y(t);
          return (
            <g key={i}>
              <line x1={PAD.left} y1={yy} x2={W - PAD.right} y2={yy} stroke="var(--line, #e2e8f0)" strokeWidth="1" />
              <text x={PAD.left - 8} y={yy + 4} textAnchor="end" fontSize="11" fill="#94a3b8">
                {t.toLocaleString("ru-RU")}
              </text>
            </g>
          );
        })}
        {/* подписи X (годы) */}
        {model.years.map((yr) => (
          <text key={yr} x={model.x(yr)} y={H - 8} textAnchor="middle" fontSize="11" fill="#94a3b8">
            {yr}
          </text>
        ))}
        {/* линии по клиникам */}
        {data.series.map((s, i) => {
          if (hidden.has(s.clinic_id) || s.points.length === 0) return null;
          const color = COLORS[i % COLORS.length];
          const pts = [...s.points].sort((a, b) => a.year - b.year);
          const d = pts.map((p, j) => `${j === 0 ? "M" : "L"} ${model.x(p.year)} ${model.y(p.price)}`).join(" ");
          return (
            <g key={s.clinic_id}>
              {pts.length > 1 && <path d={d} fill="none" stroke={color} strokeWidth="2" />}
              {pts.map((p, j) => (
                <circle key={j} cx={model.x(p.year)} cy={model.y(p.price)} r="3.5" fill={color}>
                  <title>{`${s.clinic} · ${p.year}: ${tenge(p.price)}`}</title>
                </circle>
              ))}
            </g>
          );
        })}
      </svg>

      {/* легенда — клик скрывает/показывает линию */}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5">
        {data.series.map((s, i) => {
          const color = COLORS[i % COLORS.length];
          const off = hidden.has(s.clinic_id);
          return (
            <button
              key={s.clinic_id}
              onClick={() => toggle(s.clinic_id)}
              className={`flex items-center gap-1.5 text-xs transition-opacity ${off ? "opacity-40" : ""}`}
            >
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
              <span className="text-muted">{s.clinic}</span>
              <span className="text-faint">
                ({s.points.length === 1 ? `${s.points[0].year}` : `${s.points.length} т.`})
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
