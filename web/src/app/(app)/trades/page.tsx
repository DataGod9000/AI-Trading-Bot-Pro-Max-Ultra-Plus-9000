"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ClientOnly } from "@/components/client-only";
import { apiGet } from "@/lib/api";

type Row = Record<string, unknown>;

export default function TradesPage() {
  const [closed, setClosed] = useState<Row[]>([]);
  const [openTrade, setOpenTrade] = useState<Row | null>(null);
  const [perf, setPerf] = useState<{ trade_count: number; wins: number; total_pnl: number } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    apiGet<{ closed: Row[]; open_trade: Row | null; performance: typeof perf }>("/api/trades?limit=10000")
      .then((r) => {
        setClosed(r.closed);
        setOpenTrade(r.open_trade);
        setPerf(r.performance);
      })
      .catch((e: Error) => setErr(e.message));
  }, []);

  const rows = useMemo(() => {
    return [...closed]
      .reverse()
      .map((r) => ({
        id: r.id,
        signal_id: r.signal_id,
        side: String(r.side),
        entry: Number(r.entry_price),
        exit: Number(r.exit_price),
        qty: Number(r.qty),
        pnl: Number(r.pnl),
        entry_ts: String(r.entry_ts ?? ""),
        exit_ts: String(r.exit_ts ?? ""),
        reason: String(r.exit_reason ?? ""),
      }));
  }, [closed]);

  const cumSeries = useMemo(() => {
    let c = 0;
    return rows.map((r, i) => {
      c += r.pnl;
      return { i, v: c, exit_ts: r.exit_ts };
    });
  }, [rows]);

  if (err) {
    return <p className="text-destructive">{err}</p>;
  }
  if (!perf) {
    return <p className="text-muted-foreground">Loading trades…</p>;
  }

  return (
    <div>
      <div className="mb-6 rounded-xl border border-border bg-card p-6">
        <h1 className="text-2xl font-semibold tracking-tight">Trade history & realized PnL</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Closed paper trades from SQLite and how they turned out. Daily totals elsewhere use the exit date (UTC). Not
          financial advice.
        </p>
      </div>

      {openTrade ? (
        <p className="mb-4 text-sm text-muted-foreground">
          Open position: <strong>{String(openTrade.side)}</strong> · entry $
          {Number(openTrade.entry_price).toFixed(2)} — manage on{" "}
          <a href="/paper-trading" className="text-primary underline-offset-4 hover:underline">
            Paper trading
          </a>
          .
        </p>
      ) : null}

      {!rows.length ? (
        <p className="text-muted-foreground">No closed trades yet.</p>
      ) : (
        <>
          <div className="mb-8 h-64">
            <h2 className="mb-2 text-sm font-semibold">Cumulative realized PnL</h2>
            <ClientOnly>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={cumSeries}>
                  <XAxis dataKey="i" hide />
                  <YAxis stroke="var(--muted-foreground)" fontSize={11} />
                  <Tooltip
                    contentStyle={{ background: "var(--card)", border: "1px solid var(--border)" }}
                    formatter={(v: number) => [v.toFixed(2), "cum $"]}
                  />
                  <Line type="monotone" dataKey="v" stroke="var(--primary)" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </ClientOnly>
          </div>

          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[640px] text-left text-xs">
              <thead className="bg-muted">
                <tr>
                  <th className="p-2">ID</th>
                  <th className="p-2">Side</th>
                  <th className="p-2">Entry</th>
                  <th className="p-2">Exit</th>
                  <th className="p-2">Qty</th>
                  <th className="p-2">PnL</th>
                  <th className="p-2">Exit UTC</th>
                  <th className="p-2">Reason</th>
                </tr>
              </thead>
              <tbody>
                {[...rows].reverse().map((r) => (
                  <tr key={String(r.id)} className="border-t border-border">
                    <td className="p-2 font-mono">{String(r.id)}</td>
                    <td className="p-2">{r.side}</td>
                    <td className="p-2 font-mono">{r.entry.toFixed(2)}</td>
                    <td className="p-2 font-mono">{r.exit.toFixed(2)}</td>
                    <td className="p-2 font-mono">{r.qty.toFixed(6)}</td>
                    <td className="p-2 font-mono">{r.pnl.toFixed(2)}</td>
                    <td className="p-2 font-mono">{r.exit_ts}</td>
                    <td className="p-2">{r.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
