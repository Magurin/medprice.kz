"use client";

// Рейтинг/отзывы 2ГИС: лого 2ГИС + оценка (если есть) + число отзывов, ссылка на отзывы.
// Лого и ссылка показываются всегда, когда есть url; число-оценка — когда заполнена.
export default function Rating({
  rating,
  count,
  url,
  size = "sm",
}: {
  rating?: number | null;
  count?: number | null;
  url?: string | null;
  size?: "sm" | "xs";
}) {
  if (rating == null && !url) return null;
  const cls = size === "xs" ? "text-[11px]" : "text-xs";

  // компактный знак 2ГИС (фирменный зелёный)
  const mark = (
    <span
      className={`inline-flex items-center rounded px-1 py-[1px] font-bold leading-none text-white ${
        size === "xs" ? "text-[9px]" : "text-[10px]"
      }`}
      style={{ background: "#19aa1e" }}
    >
      2ГИС
    </span>
  );

  const inner = (
    <span className={`inline-flex items-center gap-1 ${cls} font-medium text-foreground`}>
      {mark}
      {rating != null ? (
        <>
          <svg className="h-3.5 w-3.5 text-amber-400" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 17.3l-6.18 3.7 1.64-7.03L2 9.24l7.19-.61L12 2l2.81 6.63 7.19.61-5.46 4.73 1.64 7.03z" />
          </svg>
          <span className="tabular-nums">{rating.toFixed(1)}</span>
          {count != null && count > 0 && <span className="text-faint">({count})</span>}
        </>
      ) : (
        <span className="text-faint">Отзывы</span>
      )}
    </span>
  );

  if (url) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        title="Открыть отзывы в 2ГИС"
        onClick={(e) => e.stopPropagation()}
        className="hover:underline"
      >
        {inner}
      </a>
    );
  }
  return inner;
}
