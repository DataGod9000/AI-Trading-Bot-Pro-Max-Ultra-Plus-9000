"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";

type PublicWithDemo = {
  demo_snapshot?: {
    enabled?: boolean;
    last_refreshed?: string | null;
    data_range?: string | null;
    source?: string | null;
  };
};

export function SnapshotModeBanner() {
  const [demo, setDemo] = useState<PublicWithDemo["demo_snapshot"] | null>(undefined);

  useEffect(() => {
    let cancelled = false;
    apiGet<PublicWithDemo>("/api/settings/public")
      .then((r) => {
        if (!cancelled) setDemo(r.demo_snapshot ?? null);
      })
      .catch(() => {
        if (!cancelled) setDemo(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (demo === undefined || !demo?.enabled) return null;

  const refreshed = demo.last_refreshed
    ? new Date(demo.last_refreshed).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : null;

  return (
    <div
      className="border-b border-amber-500/35 bg-amber-950/40 px-4 py-2 text-sm text-amber-50/95"
      role="status"
    >
      <span className="font-semibold tracking-tight">Snapshot mode</span>
      <span className="mx-2 text-amber-200/80">·</span>
      <span className="text-amber-100/85">
        Demo data is served from precomputed files; numbers do not update until you redeploy refreshed snapshots.
      </span>
      {demo.data_range ? (
        <span className="mt-1 block text-xs text-amber-200/70 md:mt-0 md:inline md:ml-3">
          Data range: {demo.data_range}
        </span>
      ) : null}
      {refreshed ? (
        <span className="mt-1 block text-xs text-amber-200/75 md:mt-0 md:inline md:ml-3">
          Last updated: <time dateTime={demo.last_refreshed ?? undefined}>{refreshed}</time>
        </span>
      ) : null}
    </div>
  );
}
