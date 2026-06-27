import { tenge } from "@/lib/api";

// Полная шкала распределения цен для страницы услуги:
// дешёвый край слева (зелёный), дорогой справа, медиана - засечкой.
export function PriceScale({
  min,
  median,
  max,
}: {
  min: number;
  median: number;
  max: number;
}) {
  const span = Math.max(max - min, 1);
  const medianPct = Math.min(100, Math.max(0, ((median - min) / span) * 100));

  return (
    <div className="w-full">
      <div className="relative h-2.5 w-full rounded-full bg-gradient-to-r from-deal/55 via-amber-300/55 to-warn/60">
        {/* медиана */}
        <div
          className="absolute top-1/2 h-5 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground/70"
          style={{ left: `${medianPct}%` }}
          title="медиана"
        />
        {/* края */}
        <div className="absolute left-0 top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface bg-deal shadow-sm" />
        <div className="absolute right-0 top-1/2 h-4 w-4 translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface bg-warn shadow-sm" />
      </div>

      <div className="mt-2.5 flex items-center justify-between text-xs">
        <span className="font-semibold tabular-nums text-deal">{tenge(min)}</span>
        <span className="tabular-nums text-faint" style={{ marginLeft: `${medianPct - 50}%` }}>
          медиана {tenge(median)}
        </span>
        <span className="font-semibold tabular-nums text-muted">{tenge(max)}</span>
      </div>
    </div>
  );
}

// Компактная полоска разброса для карточек результатов.
export function RangeBar({ min, max, avg }: { min: number; max: number; avg: number }) {
  const span = Math.max(max - min, 1);
  const avgPct = Math.min(100, Math.max(0, ((avg - min) / span) * 100));
  return (
    <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-gradient-to-r from-deal/45 to-warn/45">
      <div
        className="absolute top-1/2 h-3 w-[2px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground/55"
        style={{ left: `${avgPct}%` }}
        title="средняя"
      />
    </div>
  );
}
