"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";

type PaperState = {
  live_price: number | null;
  live_price_error: string;
  signal_price: number;
  signal: Record<string, unknown> | null;
  technical_1h: Record<string, unknown> | null;
  technical_4h: Record<string, unknown> | null;
  open_trade: Record<string, unknown> | null;
  closed_trades: Record<string, unknown>[];
  performance: { trade_count: number; wins: number; total_pnl: number; losses?: number };
  settings: Record<string, number>;
};

function safeFloat(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

export default function PaperTradingPage() {
  const [data, setData] = useState<PaperState | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ ok: boolean; msg: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastGood, setLastGood] = useState(0);

  const load = useCallback(() => {
    apiGet<PaperState>("/api/paper/state")
      .then((s) => {
        setData(s);
        const p = s.live_price ?? 0;
        if (p > 0) {
          setLastGood(p);
        } else if (s.signal_price > 0) {
          setLastGood(s.signal_price);
        }
      })
      .catch((e: Error) => setErr(e.message));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runOrder = async (intent: "buy" | "sell" | "close") => {
    setBusy(true);
    setFlash(null);
    try {
      const r = await apiPost<{ ok: boolean; message: string }>("/api/paper/order", { intent });
      setFlash({ ok: r.ok, msg: r.message });
      load();
    } catch (e) {
      setFlash({ ok: false, msg: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const runCheckExit = async () => {
    setBusy(true);
    setFlash(null);
    try {
      const r = await apiPost<{ ok: boolean; message: string }>("/api/paper/check-exit", {});
      setFlash({ ok: r.ok, msg: r.message });
      load();
    } catch (e) {
      setFlash({ ok: false, msg: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  if (err) {
    return <p className="text-destructive">{err}</p>;
  }
  if (!data) {
    return <p className="text-muted-foreground">Loading paper trading…</p>;
  }

  const price = data.live_price && data.live_price > 0 ? data.live_price : data.signal_price;
  const tradePrice = price > 0 ? price : lastGood;
  const usingCached = price <= 0 && tradePrice > 0;

  const sig = data.signal;
  const perf = data.performance;

  return (
    <div>
      <div className="mb-6 rounded-xl border border-border bg-card p-6">
        <h1 className="text-2xl font-semibold tracking-tight">Paper trading — BTC/USD</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Simulated book in SQLite. Fills use the reference price below. TP/SL/max-hold match config — use{" "}
          <strong>Check TP/SL</strong> or <code className="rounded bg-muted px-1">btc-paper-run</code>. Not a real
          exchange.
        </p>
      </div>

      {flash ? (
        <div
          className={`mb-4 rounded-lg border p-3 text-sm ${
            flash.ok ? "border-emerald-600/50 bg-emerald-950/20" : "border-destructive/50 bg-destructive/10"
          }`}
        >
          {flash.msg}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3 md:items-stretch">
        <div className="flex min-h-[280px] flex-col rounded-xl border border-border bg-card p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-primary">Order book</h2>
          <div className="mt-4 flex-1">
            {tradePrice > 0 ? (
              <>
                <div className="font-mono text-3xl font-bold text-amber-500">
                  ${tradePrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  {usingCached
                    ? "Last known price (live quote failed)."
                    : "Reference price (CoinGecko spot or last signal)."}
                </p>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">No price yet — run the pipeline or check network.</p>
            )}
            {data.live_price_error ? (
              <p className="mt-2 text-xs text-destructive/80">{data.live_price_error}</p>
            ) : null}
          </div>
          <div className="mt-4 border-t border-border pt-4 text-sm text-muted-foreground">
            {sig ? (
              <>
                <div>
                  <strong className="text-foreground">AI signal:</strong> {String(sig.action)}
                </div>
                <div className="mt-1 text-xs">
                  UTC {String(sig.run_at)} · confidence {safeFloat(sig.confidence).toFixed(2)}
                </div>
              </>
            ) : (
              <p>No AI signal yet — manual trades still work.</p>
            )}
          </div>
        </div>

        <div className="flex min-h-[280px] flex-col rounded-xl border border-border bg-card p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-primary">Market order</h2>
          <p className="mt-2 text-xs text-muted-foreground">
            Default size ~${safeFloat(data.settings.paper_trade_usd).toFixed(0)} notional (from config).
          </p>
          <div className="mt-4 flex flex-1 flex-col justify-end gap-2">
            <button
              type="button"
              disabled={busy || tradePrice <= 0}
              onClick={() => runOrder("buy")}
              className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              Buy (market)
            </button>
            <button
              type="button"
              disabled={busy || tradePrice <= 0}
              onClick={() => runOrder("sell")}
              className="rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              Sell (market)
            </button>
            <button
              type="button"
              disabled={busy || tradePrice <= 0}
              onClick={() => runOrder("close")}
              className="rounded-md border border-border bg-muted px-3 py-2 text-sm font-medium disabled:opacity-40"
            >
              Close position
            </button>
          </div>
        </div>

        <div className="flex min-h-[280px] flex-col rounded-xl border border-border bg-card p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-primary">Risk & stats</h2>
          <button
            type="button"
            disabled={busy || tradePrice <= 0}
            onClick={runCheckExit}
            className="mt-4 rounded-md border border-primary/50 bg-primary/10 px-3 py-2 text-sm font-medium disabled:opacity-40"
          >
            Check TP / SL / max hold
          </button>
          <p className="mt-2 text-xs text-muted-foreground">
            TP +{safeFloat(data.settings.take_profit_pct)}% · SL −{safeFloat(data.settings.stop_loss_pct)}% · max hold{" "}
            {safeFloat(data.settings.max_hold_hours)}h
          </p>
          <div className="mt-4 flex-1 space-y-2 text-sm">
            <div>
              Trades: <strong>{perf.trade_count}</strong> · Win rate{" "}
              {perf.trade_count
                ? `${((safeFloat(perf.wins) / safeFloat(perf.trade_count)) * 100).toFixed(1)}%`
                : "—"}
            </div>
            <div>
              Total PnL: <strong>${safeFloat(perf.total_pnl).toFixed(2)}</strong>
            </div>
            {data.open_trade ? (
              <div className="rounded-md border border-border bg-muted/30 p-2 text-xs">
                Open: <strong>{String(data.open_trade.side)}</strong> @ $
                {safeFloat(data.open_trade.entry_price).toFixed(2)} · qty{" "}
                {safeFloat(data.open_trade.qty).toFixed(6)} BTC
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">No open position.</p>
            )}
          </div>
        </div>
      </div>

      <div className="mt-8">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">Recent closed (80)</h2>
        <div className="mt-2 max-h-72 overflow-auto rounded-lg border border-border">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-muted">
              <tr>
                <th className="p-2">Exit (UTC)</th>
                <th className="p-2">Side</th>
                <th className="p-2">PnL</th>
              </tr>
            </thead>
            <tbody>
              {data.closed_trades.map((t) => (
                <tr key={String(t.id)} className="border-t border-border">
                  <td className="p-2 font-mono">{String(t.exit_ts ?? "")}</td>
                  <td className="p-2">{String(t.side)}</td>
                  <td className="p-2 font-mono">{safeFloat(t.pnl).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
