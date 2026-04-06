"use client";

import { useEffect, useState } from "react";

/**
 * Renders children only after mount so Recharts / DOM-measured layouts do not
 * SSR with different dimensions than the client (fixes hard-refresh / hydration issues).
 */
export function ClientOnly({
  children,
  fallback,
}: {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setReady(true);
  }, []);
  if (!ready) {
    return (
      fallback ?? <div className="h-64 w-full animate-pulse rounded-lg bg-muted/40" aria-hidden />
    );
  }
  return <>{children}</>;
}
