"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ClientOnly } from "@/components/client-only";
import AnimatedDownloadButton from "@/components/ui/download-hover-button";
import { apiGet } from "@/lib/api";

type WindowRow = {
  train_start: string;
  train_end: string;
  test_start: string;
  test_end: string;
  summary: Record<string, number>;
};

type Pt = { ts: string; equity?: number };

type Resp = {
  summary: { oos_cumulative_return: number; windows: number } | null;
  equity_curve: Pt[];
  windows: WindowRow[];
};

function pct(n: number) {
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

export default function WalkForwardPage() {
  const [data, setData] = useState<Resp | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [reconstruct, setReconstruct] = useState(false);
  const [sizingMode, setSizingMode] = useState("confidence");
  const [buyTh, setBuyTh] = useState(0.08);
  const [sellTh, setSellTh] = useState(-0.08);
  const [feeBps, setFeeBps] = useState(0);
  const [slipBps, setSlipBps] = useState(0);
  const [trainBars, setTrainBars] = useState(24 * 30);
  const [testBars, setTestBars] = useState(24 * 7);
  const [stepBars, setStepBars] = useState(24 * 7);

  const run = async () => {
    setRunning(true);
    setErr(null);
    try {
      const qs = new URLSearchParams();
      qs.set("sizing_mode", sizingMode);
      qs.set("buy_threshold", String(buyTh));
      qs.set("sell_threshold", String(sellTh));
      qs.set("fee_bps", String(feeBps));
      qs.set("slippage_bps", String(slipBps));
      qs.set("train_bars", String(trainBars));
      qs.set("test_bars", String(testBars));
      qs.set("step_bars", String(stepBars));
      if (reconstruct) {
        qs.set("reconstruct_signal", "true");
        qs.set("news_lookback_hours", "24");
      }
      const r = await apiGet<Resp>(`/api/backtest/walkforward?${qs.toString()}`, { timeoutMs: 180_000 });
      setData(r);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const curve = useMemo(() => {
    if (!data) return [];
    return (data.equity_curve ?? []).map((p) => ({ ts: p.ts.slice(0, 10), equity: p.equity ?? 0 }));
  }, [data]);

  if (err) return <p className="text-destructive">{err}</p>;
  if (!data) return <p className="text-muted-foreground">Loading walk-forward…</p>;

  return (
    <div>
      <div className="mb-6 rounded-xl border border-border bg-card p-6">
        <h1 className="text-2xl font-semibold tracking-tight text-white">Backtesting · Walk-forward</h1>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          Walk-forward is a tougher way to evaluate a strategy. We test on rolling out-of-sample windows and stitch the
          results into one continuous curve. This first pass does <strong>not</strong> retrain ML models yet. It evaluates
          the historical unified score in sequential test windows.
        </p>
        <p className="mt-3 text-sm text-muted-foreground">
          Out-of-sample cumulative return:{" "}
          <span className="font-mono text-foreground">
            {data.summary ? pct(data.summary.oos_cumulative_return) : "—"}
          </span>
        </p>
        <div className="mt-4 flex flex-col gap-3 rounded-lg border border-border/60 bg-background/30 p-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="grid gap-3 sm:grid-cols-5">
            <label className="text-xs text-muted-foreground">
              Sizing
              <select
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground"
                value={sizingMode}
                onChange={(e) => setSizingMode(e.target.value)}
              >
                <option value="fixed">fixed</option>
                <option value="confidence">confidence</option>
                <option value="confidence_vol">confidence_vol</option>
              </select>
            </label>
            <label className="text-xs text-muted-foreground">
              Buy threshold (score)
              <input
                type="number"
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground"
                value={buyTh}
                step={0.01}
                onChange={(e) => setBuyTh(Number(e.target.value))}
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Sell threshold (score)
              <input
                type="number"
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground"
                value={sellTh}
                step={0.01}
                onChange={(e) => setSellTh(Number(e.target.value))}
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Fee (bps)
              <input
                type="number"
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground"
                value={feeBps}
                min={0}
                step={1}
                onChange={(e) => setFeeBps(Number(e.target.value))}
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Slippage (bps)
              <input
                type="number"
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground"
                value={slipBps}
                min={0}
                step={1}
                onChange={(e) => setSlipBps(Number(e.target.value))}
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Train bars
              <input
                type="number"
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground"
                value={trainBars}
                min={24}
                step={24}
                onChange={(e) => setTrainBars(Number(e.target.value))}
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Test bars
              <input
                type="number"
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground"
                value={testBars}
                min={24}
                step={24}
                onChange={(e) => setTestBars(Number(e.target.value))}
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Step bars
              <input
                type="number"
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground"
                value={stepBars}
                min={24}
                step={24}
                onChange={(e) => setStepBars(Number(e.target.value))}
              />
            </label>
            <label className="flex items-center gap-2 pt-6 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={reconstruct}
                onChange={(e) => setReconstruct(e.target.checked)}
              />
              Reconstruct signal retroactively (no lookahead)
            </label>
          </div>
          <AnimatedDownloadButton
            variant="primary"
            label="Run walk-forward"
            expandedWidth={260}
            pending={running}
            disabled={running}
            onClick={() => void run()}
          />
        </div>
        {running ? (
          <div className="mt-3 overflow-hidden rounded-md border border-border/60 bg-background/40">
            <div className="relative h-2 w-full">
              <div className="absolute inset-0 bg-muted/30" />
              <div className="btc-indeterminate-bar absolute inset-y-0 left-0 w-1/3 bg-foreground/80" />
            </div>
            <div className="px-3 py-2 text-xs text-muted-foreground">Running walk-forward…</div>
          </div>
        ) : null}
        {err ? <p className="mt-3 text-sm text-destructive">{err}</p> : null}
      </div>

      <div className="mb-8 rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold text-white">Out-of-sample equity curve</h2>
        <ClientOnly fallback={<div className="mt-4 h-[300px] animate-pulse rounded-lg bg-muted/30" />}>
          <div className="mt-4 h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={curve} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="ts" tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} />
                <YAxis tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} width={60} />
                <Tooltip
                  contentStyle={{
                    background: "var(--card)",
                    border: "1px solid var(--border)",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                />
                <Line type="monotone" dataKey="equity" stroke="var(--foreground)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </ClientOnly>
      </div>

      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold text-white">Windows</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr>
                <th className="py-2 pr-3">Train</th>
                <th className="py-2 pr-3">Test</th>
                <th className="py-2 pr-3">Cumulative</th>
                <th className="py-2 pr-3">Sharpe</th>
                <th className="py-2">Max DD</th>
              </tr>
            </thead>
            <tbody>
              {data.windows.map((w, i) => (
                <tr key={i} className="border-t border-border/60">
                  <td className="py-2 pr-3 font-mono text-xs">
                    {w.train_start.slice(0, 10)} → {w.train_end.slice(0, 10)}
                  </td>
                  <td className="py-2 pr-3 font-mono text-xs">
                    {w.test_start.slice(0, 10)} → {w.test_end.slice(0, 10)}
                  </td>
                  <td className="py-2 pr-3 font-mono">{pct(w.summary.cumulative_return ?? 0)}</td>
                  <td className="py-2 pr-3 font-mono">{Number(w.summary.sharpe ?? 0).toFixed(3)}</td>
                  <td className="py-2 font-mono">{pct(w.summary.max_drawdown ?? 0)}</td>
                </tr>
              ))}
              {!data.windows.length ? (
                <tr>
                  <td colSpan={5} className="py-6 text-sm text-muted-foreground">
                    Not enough history for the default windows yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

