"use client";

import { useCallback, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";

type PriceResp = { price: number | null; error: string | null };

type LiveStatus = "idle" | "loading" | "success" | "timeout" | "unavailable";

function statusLabel(s: LiveStatus): string {
  if (s === "success") return "Success";
  if (s === "timeout") return "Timeout";
  if (s === "unavailable") return "Unavailable";
  if (s === "loading") return "Loading…";
  return "—";
}

function StatusPill({ status }: { status: LiveStatus }) {
  const cls =
    status === "success"
      ? "border-emerald-500/50 bg-emerald-950/40 text-emerald-100"
      : status === "timeout"
        ? "border-amber-500/50 bg-amber-950/30 text-amber-100"
        : status === "unavailable"
          ? "border-red-500/40 bg-red-950/30 text-red-100"
          : status === "loading"
            ? "border-border bg-muted/40 text-muted-foreground"
            : "border-border bg-background/40 text-muted-foreground";
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${cls}`}>
      {statusLabel(status)}
    </span>
  );
}

export default function LiveTestPage() {
  const [price, setPrice] = useState<PriceResp | null>(null);
  const [priceStatus, setPriceStatus] = useState<LiveStatus>("idle");
  const [priceErr, setPriceErr] = useState<string | null>(null);

  const [tech, setTech] = useState<Record<string, unknown> | null>(null);
  const [techStatus, setTechStatus] = useState<LiveStatus>("idle");
  const [techErr, setTechErr] = useState<string | null>(null);

  const [syncResult, setSyncResult] = useState<Record<string, unknown> | null>(null);
  const [syncStatus, setSyncStatus] = useState<LiveStatus>("idle");
  const [syncErr, setSyncErr] = useState<string | null>(null);

  const fetchPrice = useCallback(() => {
    setPriceStatus("loading");
    setPriceErr(null);
    apiGet<PriceResp>("/api/price/live", { timeoutMs: 30_000 })
      .then((r) => {
        setPrice(r);
        if (r.error) {
          setPriceStatus("unavailable");
          setPriceErr(r.error);
        } else {
          setPriceStatus("success");
        }
      })
      .catch((e: Error) => {
        setPrice(null);
        const msg = e.message.toLowerCase();
        if (msg.includes("timed out") || msg.includes("timeout")) setPriceStatus("timeout");
        else setPriceStatus("unavailable");
        setPriceErr(e.message);
      });
  }, []);

  const fetchTechnical = useCallback(() => {
    setTechStatus("loading");
    setTechErr(null);
    setTech(null);
    apiGet<Record<string, unknown>>("/api/technical/live?chart_points=120", { timeoutMs: 120_000 })
      .then((r) => {
        setTech(r);
        if (r.spot_error && !r.spot_usd) setTechStatus("unavailable");
        else setTechStatus("success");
      })
      .catch((e: Error) => {
        const msg = e.message.toLowerCase();
        if (msg.includes("timed out") || msg.includes("timeout")) setTechStatus("timeout");
        else setTechStatus("unavailable");
        setTechErr(e.message);
      });
  }, []);

  const runNewsSync = useCallback(() => {
    setSyncStatus("loading");
    setSyncErr(null);
    setSyncResult(null);
    apiPost<Record<string, unknown>>("/api/news/sync", undefined, { timeoutMs: 300_000 })
      .then((r) => {
        setSyncResult(r);
        setSyncStatus("success");
      })
      .catch((e: Error) => {
        const msg = e.message.toLowerCase();
        if (msg.includes("timed out") || msg.includes("timeout")) setSyncStatus("timeout");
        else setSyncStatus("unavailable");
        setSyncErr(e.message);
      });
  }, []);

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-border bg-card p-6">
        <h1 className="text-2xl font-semibold tracking-tight text-white">Live Test</h1>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          Optional live checks (price, technicals, news sync). Isolated from Overview and snapshot-backed pages:
          failures here show as status below and do not block the rest of the app.
        </p>
      </div>

      <section className="rounded-xl border border-border bg-card p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">Live BTC price</h2>
            <p className="mt-1 text-xs text-muted-foreground">GET /api/price/live</p>
          </div>
          <StatusPill status={priceStatus} />
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={fetchPrice}
            disabled={priceStatus === "loading"}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-foreground hover:bg-muted/50 disabled:opacity-50"
          >
            {priceStatus === "loading" ? "Fetching…" : "Fetch price"}
          </button>
          {price?.price != null ? (
            <span className="font-mono text-lg text-foreground">${price.price.toFixed(2)}</span>
          ) : null}
        </div>
        {priceErr ? <p className="mt-3 text-sm text-amber-600 dark:text-amber-400">{priceErr}</p> : null}
      </section>

      <section className="rounded-xl border border-border bg-card p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">Live technical analysis</h2>
            <p className="mt-1 text-xs text-muted-foreground">GET /api/technical/live — CoinGecko + indicators.</p>
          </div>
          <StatusPill status={techStatus} />
        </div>
        <div className="mt-4">
          <button
            type="button"
            onClick={fetchTechnical}
            disabled={techStatus === "loading"}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-foreground hover:bg-muted/50 disabled:opacity-50"
          >
            {techStatus === "loading" ? "Running…" : "Refresh technicals"}
          </button>
        </div>
        {techErr ? (
          <p className="mt-3 text-sm text-amber-600 dark:text-amber-400">{techErr}</p>
        ) : tech ? (
          <pre className="mt-4 max-h-80 overflow-auto rounded-lg border border-border/60 bg-background/50 p-3 text-xs text-muted-foreground">
            {JSON.stringify(
              {
                spot_usd: tech.spot_usd,
                spot_error: tech.spot_error,
                technical_score: tech.technical_score,
                blend_explanation: tech.blend_explanation,
                err_1h: tech.err_1h,
                err_4h: tech.err_4h,
              },
              null,
              2,
            )}
          </pre>
        ) : null}
      </section>

      <section className="rounded-xl border border-border bg-card p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">News sentiment sync</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              POST /api/news/sync — FinBERT + DB (does not update snapshot files).
            </p>
          </div>
          <StatusPill status={syncStatus} />
        </div>
        <div className="mt-4">
          <button
            type="button"
            onClick={runNewsSync}
            disabled={syncStatus === "loading"}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-foreground hover:bg-muted/50 disabled:opacity-50"
          >
            {syncStatus === "loading" ? "Syncing…" : "Run news sync"}
          </button>
        </div>
        {syncErr ? <p className="mt-3 text-sm text-amber-600 dark:text-amber-400">{syncErr}</p> : null}
        {syncResult ? (
          <pre className="mt-4 max-h-64 overflow-auto rounded-lg border border-border/60 bg-background/50 p-3 text-xs text-muted-foreground">
            {JSON.stringify(syncResult, null, 2)}
          </pre>
        ) : null}
      </section>
    </div>
  );
}
