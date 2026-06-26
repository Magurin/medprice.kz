"use client";

// Заглушка: очередь ручной разметки (unmatched_queue) — сопоставление
// непривязанных строк прайса с канонической услугой.
export default function QueuePage() {
  return (
    <div className="rounded-2xl border border-dashed border-line2 bg-surface p-8 text-center">
      <h2 className="text-base font-semibold text-foreground">Очередь разметки</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted">
        Здесь будут строки прайсов, не привязанные к справочнику, и ручное сопоставление с
        канонической услугой. В разработке.
      </p>
    </div>
  );
}
