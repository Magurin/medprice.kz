"use client";

// Залитое поле ввода для auth-форм (светло-серая заливка, фокус - бирюзовая рамка).
export default function AuthField({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  autoComplete,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
  autoComplete?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-muted">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        className="w-full rounded-xl border border-line bg-background px-3.5 py-2.5 text-sm text-foreground outline-none transition-colors placeholder:text-faint focus:border-brand focus:bg-surface"
      />
    </label>
  );
}
