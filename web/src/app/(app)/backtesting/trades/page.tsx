"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet } from "@/lib/api";

type Trade = {
  entry_ts: string;
  exit_ts: string;
  side: string;
  size: number;
  entry_price: number;
  exit_price: number;
  holding_bars: number;
  gross_return: number;
  net_return: number;
  gross_pnl: number;
  net_pnl: number;
};

type Resp = { trades: Trade[] };

function pct(n: number) {
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

export default function BacktestTradesPage() {
  const [data, setData] = useState<Trade[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    setErr(null);
    apiGet<Resp>("/api/backtest/trades")
      .then((r) => setData(r.trades))
      .catch((e: Error) => setErr(e.message));
  }, []);

  const rows = useMemo(() => {
    const qq = q.trim().toLowerCase();
    if (!qq) return data;
    return data.filter((t) => {
      const s = `${t.side} ${t.entry_ts} ${t.exit_ts}`.toLowerCase();
      return s.includes(qq);
    });
  }, [data, q]);

  return (
    <div>
      <div className="mb-6 rounded-xl border border-border bg-card p-6">
        <h1 className="text-2xl font-semibold tracking-tight text-white">Backtesting · Trade log</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Trades reconstructed from the executed position series using simple entry and exit rules. Great for reviewing
          behavior and edge cases, not a tick-level execution simulator.
        </p>
        <div className="mt-4 flex items-center gap-3">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter (side or date)…"
            className="w-full max-w-sm rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
          />
          <div className="text-xs text-muted-foreground">
            {rows.length} / {data.length}
          </div>
        </div>
        {err ? <p className="mt-3 text-sm text-destructive">{err}</p> : null}
      </div>

      <div className="overflow-x-auto rounded-xl border border-border bg-card">
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-3">Entry</th>
              <th className="px-4 py-3">Exit</th>
              <th className="px-4 py-3">Side</th>
              <th className="px-4 py-3">Size</th>
              <th className="px-4 py-3">Net return</th>
              <th className="px-4 py-3">Net PnL</th>
              <th className="px-4 py-3">Hold (bars)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t, i) => (
              <tr key={`${t.entry_ts}-${i}`} className="border-t border-border/60">
                <td className="px-4 py-3 font-mono text-xs">{t.entry_ts}</td>
                <td className="px-4 py-3 font-mono text-xs">{t.exit_ts}</td>
                <td className="px-4 py-3 font-mono">{t.side}</td>
                <td className="px-4 py-3 font-mono">{t.size.toFixed(3)}</td>
                <td className="px-4 py-3 font-mono">{pct(t.net_return)}</td>
                <td className="px-4 py-3 font-mono">${t.net_pnl.toFixed(2)}</td>
                <td className="px-4 py-3 font-mono">{t.holding_bars}</td>
              </tr>
            ))}
            {!rows.length ? (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-sm text-muted-foreground">
                  No trades yet. You probably don’t have much historical signal history in SQLite yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

