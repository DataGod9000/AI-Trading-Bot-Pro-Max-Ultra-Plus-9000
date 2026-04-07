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

type BacktestSummary = {
  cumulative_return: number;
  annualized_return: number;
  annualized_volatility: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  calmar: number;
  win_rate: number;
  trade_count: number;
  avg_trade_return: number;
  total_turnover: number;
  total_cost_paid: number;
  benchmark_cumulative_return: number;
  alpha_vs_benchmark: number;
};

type Pt = { ts: string; equity?: number; drawdown?: number; exposure?: number };

type BacktestRun = {
  summary: BacktestSummary;
  equity_curve: Pt[];
  drawdown_curve: Pt[];
  benchmark_curve: Pt[];
  exposure_curve: Pt[];
  params: Record<string, unknown>;
  dataset_source: string;
  bars: number;
};

function pct(n: number) {
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

function num(n: number) {
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(3);
}

function Metric({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-lg border border-border/80 bg-background/40 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{k}</div>
      <div className="mt-0.5 font-mono text-lg text-foreground">{v}</div>
    </div>
  );
}

function RunningBar({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <div className="mt-3 overflow-hidden rounded-md border border-border/60 bg-background/40">
      <div className="relative h-2 w-full">
        <div className="absolute inset-0 bg-muted/30" />
        <div className="btc-indeterminate-bar absolute inset-y-0 left-0 w-1/3 bg-foreground/80" />
      </div>
      <div className="px-3 py-2 text-xs text-muted-foreground">Running backtest…</div>
    </div>
  );
}

export default function BacktestingPage() {
  const [data, setData] = useState<BacktestRun | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [reconstruct, setReconstruct] = useState(false);
  const [feeBps, setFeeBps] = useState(0);
  const [slipBps, setSlipBps] = useState(0);
  const [sizingMode, setSizingMode] = useState("confidence");
  const [buyTh, setBuyTh] = useState(0.08);
  const [sellTh, setSellTh] = useState(-0.08);

  const run = async () => {
    setRunning(true);
    setErr(null);
    try {
      const qs = new URLSearchParams();
      qs.set("fee_bps", String(feeBps));
      qs.set("slippage_bps", String(slipBps));
      qs.set("sizing_mode", sizingMode);
      qs.set("buy_threshold", String(buyTh));
      qs.set("sell_threshold", String(sellTh));
      if (reconstruct) {
        qs.set("reconstruct_signal", "true");
        qs.set("news_lookback_hours", "24");
      }
      const r = await apiGet<BacktestRun>(`/api/backtest/run?${qs.toString()}`, { timeoutMs: 180_000 });
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

  const equity = useMemo(() => {
    if (!data) return [];
    const benchByTs = new Map(data.benchmark_curve.map((p) => [p.ts, p.equity ?? 0]));
    return data.equity_curve.map((p) => ({
      ts: p.ts.slice(0, 10),
      strategy: p.equity ?? 0,
      benchmark: benchByTs.get(p.ts) ?? 0,
    }));
  }, [data]);

  const dd = useMemo(() => {
    if (!data) return [];
    return data.drawdown_curve.map((p) => ({
      ts: p.ts.slice(0, 10),
      drawdown: p.drawdown ?? 0,
    }));
  }, [data]);

  if (err) return <p className="text-destructive">{err}</p>;
  if (!data) return <p className="text-muted-foreground">Loading backtest…</p>;

  const s = data.summary;

  return (
    <div>
      <div className="mb-6 rounded-xl border border-border bg-card p-6">
        <h1 className="text-2xl font-semibold tracking-tight text-white">Backtesting</h1>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          Backtest your existing unified <span className="font-mono text-foreground">final_score</span> on historical
          bars using next-bar execution (signal at <span className="font-mono">t</span>, fill at{" "}
          <span className="font-mono">t+1</span>). No lookahead. Fees and slippage only apply when exposure changes.
        </p>
        <div className="mt-4 flex flex-col gap-3 rounded-lg border border-border/60 bg-background/30 p-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="grid gap-3 sm:grid-cols-6">
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
            label="Run backtest"
            expandedWidth={220}
            pending={running}
            disabled={running}
            onClick={() => void run()}
          />
        </div>
        <RunningBar show={running} />
        <p className="mt-2 text-xs text-muted-foreground">
          Dataset: <span className="font-mono text-foreground">{data.dataset_source}</span> · bars{" "}
          <span className="font-mono text-foreground">{data.bars}</span>
        </p>
        {data.summary.trade_count === 0 ? (
          <p className="mt-2 text-xs text-muted-foreground">
            Strategy is currently <strong className="text-foreground">flat</strong> (no threshold crossings), so returns
            are ~0 while the benchmark still moves. Try lowering thresholds (e.g. 0.05 / -0.05) or enabling retroactive
            reconstruction.
          </p>
        ) : null}
        <div className="mt-4 flex flex-wrap gap-3 text-sm">
          <a className="btc-nav-link inline-flex w-auto" href="/backtesting/compare">
            Strategy comparison
          </a>
          <a className="btc-nav-link inline-flex w-auto" href="/backtesting/trades">
            Trade log
          </a>
          <a className="btc-nav-link inline-flex w-auto" href="/backtesting/walkforward">
            Walk-forward
          </a>
        </div>
      </div>

      <div className="mb-8 rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold text-white">Headline metrics</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric k="Cumulative return" v={pct(s.cumulative_return)} />
          <Metric k="Ann. return" v={pct(s.annualized_return)} />
          <Metric k="Ann. vol" v={pct(s.annualized_volatility)} />
          <Metric k="Sharpe" v={num(s.sharpe)} />
          <Metric k="Sortino" v={num(s.sortino)} />
          <Metric k="Max drawdown" v={pct(s.max_drawdown)} />
          <Metric k="Trades (approx)" v={String(s.trade_count)} />
          <Metric k="Alpha vs buy&hold" v={pct(s.alpha_vs_benchmark)} />
        </div>
      </div>

      <div className="grid gap-8 lg:grid-cols-2">
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="text-sm font-semibold text-white">Equity curve (strategy vs benchmark)</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Benchmark is BTC buy-and-hold on the same bars. Values are equity, not returns.
          </p>
          <ClientOnly fallback={<div className="mt-4 h-[260px] animate-pulse rounded-lg bg-muted/30" />}>
            <div className="mt-4 h-[260px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={equity} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
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
                  <Line type="monotone" dataKey="strategy" stroke="var(--foreground)" strokeWidth={2} dot={false} />
                  <Line
                    type="monotone"
                    dataKey="benchmark"
                    stroke="var(--muted-foreground)"
                    strokeDasharray="4 4"
                    strokeWidth={1.5}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </ClientOnly>
        </div>

        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="text-sm font-semibold text-white">Drawdown</h3>
          <p className="mt-1 text-xs text-muted-foreground">Peak-to-trough drawdown of the strategy equity curve.</p>
          <ClientOnly fallback={<div className="mt-4 h-[260px] animate-pulse rounded-lg bg-muted/30" />}>
            <div className="mt-4 h-[260px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={dd} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                  <XAxis dataKey="ts" tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} />
                  <YAxis tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} width={60} />
                  <Tooltip
                    formatter={(v: number) => `${(v * 100).toFixed(2)}%`}
                    contentStyle={{
                      background: "var(--card)",
                      border: "1px solid var(--border)",
                      borderRadius: "8px",
                      fontSize: "12px",
                    }}
                  />
                  <Line type="monotone" dataKey="drawdown" stroke="#ef4444" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </ClientOnly>
        </div>
      </div>
    </div>
  );
}

