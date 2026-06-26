"use client";

import { addToBasket, removeFromBasket, useBasket } from "@/lib/basket";

export default function AddToBasketButton({ code, name }: { code: string; name: string }) {
  const items = useBasket();
  const added = items.some((i) => i.code === code);

  return (
    <button
      onClick={() => (added ? removeFromBasket(code) : addToBasket({ code, name }))}
      className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-medium transition-colors ${
        added
          ? "border-deal/40 bg-deal-tint text-deal"
          : "border-line2 bg-surface text-foreground hover:bg-surface2"
      }`}
    >
      {added ? (
        <>
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M20 6 9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          В корзине сравнения
        </>
      ) : (
        <>
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 5v14M5 12h14" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          В сравнение
        </>
      )}
    </button>
  );
}
