interface CardProps {
  title?: string;
  children: React.ReactNode;
  className?: string;
}

export default function Card({ title, children, className = "" }: CardProps) {
  return (
    <div className={`bg-panel rounded-2xl border border-line ${className}`}>
      {title && (
        <div className="px-6 py-4 border-b border-line">
          <h2 className="font-display text-sm font-semibold text-slate-300 uppercase tracking-wide">
            {title}
          </h2>
        </div>
      )}
      <div className="p-6">{children}</div>
    </div>
  );
}

export function StatCard({
  label,
  value,
  unit,
  color = "text-emerald-400",
}: {
  label: string;
  value: string | number | null | undefined;
  unit?: string;
  color?: string;
}) {
  return (
    <div className="bg-panel rounded-2xl border border-line p-5">
      <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-1">{label}</p>
      <p className={`font-display text-2xl font-bold ${color}`}>
        {value ?? "—"}
        {value != null && unit && (
          <span className="text-sm font-normal text-slate-500 ml-1">{unit}</span>
        )}
      </p>
    </div>
  );
}
