"use client";

import { useEffect, useMemo, useState } from "react";
import { Computing } from "@/components/ui/computing";

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-muted/50 ${className}`} />;
}

export function ChartSkeleton({ label }: { label: string }) {
  return (
    <div className="relative h-full w-full overflow-hidden rounded-lg border border-border/60 bg-muted/20">
      <div className="absolute inset-0 animate-pulse bg-muted/30" />
      <div className="absolute left-3 top-3 rounded-full border border-border bg-background/70 px-2.5 py-1 text-xs text-muted-foreground">
        {label}
      </div>
    </div>
  );
}

export function MetricGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-[52px]" />
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 8, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="bg-muted px-3 py-2">
        <Skeleton className="h-4 w-40" />
      </div>
      <div className="divide-y divide-border">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="grid gap-3 px-3 py-3" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
            {Array.from({ length: cols }).map((__, c) => (
              <Skeleton key={c} className="h-3 w-full" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function RotatingLoadingMessage({
  messages,
  intervalMs = 900,
  className = "",
}: {
  messages: string[];
  intervalMs?: number;
  className?: string;
}) {
  const safe = useMemo(() => (messages.length ? messages : ["Computing…"]), [messages]);
  const [i, setI] = useState(0);

  useEffect(() => {
    if (safe.length <= 1) return;
    const t = setInterval(() => setI((x) => (x + 1) % safe.length), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs, safe.length]);

  return <Computing className={className} label={safe[i]} />;
}

