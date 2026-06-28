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
    const allPrices = data.series.flatMap((s) => s.points.map((p) => p.price));
    if (allPrices.length === 0) return null;
    const minP = Math.min(...allPrices);
    const maxP = Math.max(...allPrices);
    const span = maxP - minP || maxP || 1;
    // отступ диапазона, чтобы линии не липли к краям
    const lo = Math.max(0, minP - span * 0.15);
    const hi = maxP + span * 0.15;

    // ось X — по реальным датам (внутригодовые изменения тоже видны)
    const t = (iso: string) => new Date(iso).getTime();
    const times = data.series.flatMap((s) => s.points.map((p) => t(p.date)));
    const minT = Math.min(...times);
    const maxT = Math.max(...times);
    const tSpan = maxT - minT || 1;

    const x = (iso: string) =>
      PAD.left + ((t(iso) - minT) / tSpan) * (W - PAD.left - PAD.right);
    const y = (price: number) =>
      PAD.top + (1 - (price - lo) / (hi - lo)) * (H - PAD.top - PAD.bottom);

    // подписи X: 4 равномерных отметки по времени; формат зависит от охвата
    const overYear = maxT - minT > 400 * 86400_000;
    const fmt = (ms: number) =>
      new Date(ms).toLocaleDateString("ru-RU", overYear
        ? { year: "numeric" }
        : { day: "2-digit", month: "short" });
    const xTicks = (minT === maxT
      ? [minT]
      : Array.from({ length: 4 }, (_, i) => minT + (tSpan * i) / 3)
    ).map((ms) => ({
      label: fmt(ms),
      px: PAD.left + ((ms - minT) / tSpan) * (W - PAD.left - PAD.right),
    }));

    return { lo, hi, x, y, xTicks };
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
        {/* подписи X (даты) */}
        {model.xTicks.map((tk, i) => (
          <text key={i} x={tk.px} y={H - 8} textAnchor="middle" fontSize="11" fill="#94a3b8">
            {tk.label}
          </text>
        ))}
        {/* линии по клиникам */}
        {data.series.map((s, i) => {
          if (hidden.has(s.clinic_id) || s.points.length === 0) return null;
          const color = COLORS[i % COLORS.length];
          const pts = [...s.points].sort((a, b) => +new Date(a.date) - +new Date(b.date));
          const d = pts.map((p, j) => `${j === 0 ? "M" : "L"} ${model.x(p.date)} ${model.y(p.price)}`).join(" ");
          return (
            <g key={s.clinic_id}>
              {pts.length > 1 && <path d={d} fill="none" stroke={color} strokeWidth="2" />}
              {pts.map((p, j) => (
                <circle key={j} cx={model.x(p.date)} cy={model.y(p.price)} r="3.5" fill={color}>
                  <title>{`${s.clinic} · ${new Date(p.date).toLocaleDateString("ru-RU")}: ${tenge(p.price)}`}</title>
                </circle>
              ))}
            </g>
          );
        })}
      </svg>

      {/* легенда - клик скрывает/показывает линию */}
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
