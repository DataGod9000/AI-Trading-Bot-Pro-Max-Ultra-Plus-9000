"use client";

export function ScoreBar({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(100, ((score + 1) / 2) * 100));
  return (
    <div className="relative mt-2 h-2.5 w-full rounded-sm bg-muted">
      <div className="absolute left-1/2 top-0 h-full w-0.5 -translate-x-1/2 bg-border" />
      <div
        className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-card bg-primary shadow-[0_0_0_2px_rgba(0,119,188,0.35)]"
        style={{ left: `${pct}%` }}
      />
    </div>
  );
}
