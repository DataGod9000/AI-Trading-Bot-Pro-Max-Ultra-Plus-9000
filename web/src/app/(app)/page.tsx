"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ClientOnly } from "@/components/client-only";
import { apiGet } from "@/lib/api";

function safeFloat(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

type LatestSignalResp = { signal: Record<string, unknown> | null };

type PublicSettingsResp = {
  backtest_defaults?: {
    buy_threshold?: number;
    sell_threshold?: number;
    fee_bps?: number;
    slippage_bps?: number;
    sizing_mode?: string;
    vol_window?: number;
    max_position_size?: number;
    target_volatility?: number;
    initial_capital?: number;
  };
};

type BacktestSummary = {
  cumulative_return: number;
  sharpe: number;
  max_drawdown: number;
  win_rate: number;
  trade_count: number;
  alpha_vs_benchmark: number;
  benchmark_cumulative_return: number;
};

type Pt = { ts: string; equity?: number; drawdown?: number; exposure?: number; final_score?: number };

type BacktestRun = {
  summary: BacktestSummary;
  equity_curve: Pt[];
  drawdown_curve: Pt[];
  benchmark_curve: Pt[];
  exposure_curve: Pt[];
  score_curve?: Pt[];
  params: Record<string, unknown>;
  dataset_source: string;
  bars: number;
};

function fmtPct(n: number) {
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

function fmtNum(n: number) {
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(3);
}

function signalLabelFromAction(action: string): "LONG" | "SHORT" | "FLAT" {
  const a = (action || "").toUpperCase();
  if (a === "BUY") return "LONG";
  if (a === "SELL") return "SHORT";
  return "FLAT";
}

function signalPillClass(lbl: "LONG" | "SHORT" | "FLAT") {
  if (lbl === "LONG") return "bg-emerald-600 text-white";
  if (lbl === "SHORT") return "bg-red-600 text-white";
  return "border border-border bg-muted text-muted-foreground";
}

/** API JSON can stringify some numerics oddly; coerce so summary always matches headline cards. */
function normalizeSummary(raw: unknown): BacktestSummary {
  const o = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  return {
    cumulative_return: safeFloat(o.cumulative_return),
    sharpe: safeFloat(o.sharpe),
    max_drawdown: safeFloat(o.max_drawdown),
    win_rate: safeFloat(o.win_rate),
    trade_count: Math.round(safeFloat(o.trade_count)),
    alpha_vs_benchmark: safeFloat(o.alpha_vs_benchmark),
    benchmark_cumulative_return: safeFloat(o.benchmark_cumulative_return),
  };
}

function interpretSummary(s: BacktestSummary): string[] {
  const out: string[] = [];
  const alpha = s.alpha_vs_benchmark;
  const bench = s.benchmark_cumulative_return;
  const strat = s.cumulative_return;
  if (Number.isFinite(alpha) && Number.isFinite(strat) && Number.isFinite(bench)) {
    const verb = alpha >= 0 ? "outperformed" : "underperformed";
    out.push(`Strategy ${verb} BTC buy-and-hold by ${fmtPct(Math.abs(alpha))} over the tested period.`);
  }
  if (Number.isFinite(s.sharpe)) {
    const tag = s.sharpe >= 1 ? "strong" : s.sharpe >= 0.5 ? "moderate" : "weak";
    out.push(`Sharpe of ${fmtNum(s.sharpe)} suggests ${tag} risk-adjusted returns (higher is better).`);
  }
  if (Number.isFinite(s.max_drawdown)) {
    out.push(`Worst peak-to-trough drawdown was ${fmtPct(s.max_drawdown)}.`);
  }
  if (Number.isFinite(s.trade_count) && Number.isFinite(s.win_rate)) {
    out.push(`Win rate was ${fmtPct(s.win_rate)} across ${Math.round(s.trade_count)} simulated trades.`);
  }
  return out.slice(0, 3);
}

const CHART_MAX_POINTS = 220;

function downsampleRows<T>(rows: T[], maxPoints: number): T[] {
  if (rows.length <= maxPoints) return rows;
  const step = Math.ceil(rows.length / maxPoints);
  const out: T[] = [];
  let lastPushed = -1;
  for (let i = 0; i < rows.length; i += step) {
    out.push(rows[i]);
    lastPushed = i;
  }
  if (lastPushed !== rows.length - 1) out.push(rows[rows.length - 1]);
  return out;
}

function TooltipBox({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-border bg-card px-3 py-2 text-xs text-muted-foreground">
      <div className="font-mono text-foreground">{String(label)}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="mt-1 flex items-center justify-between gap-6">
          <span>{String(p.name ?? p.dataKey)}</span>
          <span className="font-mono text-foreground">
            {Number.isFinite(Number(p.value)) ? Number(p.value).toFixed(3) : String(p.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function OverviewPage() {
  const [sig, setSig] = useState<Record<string, unknown> | null>(null);
  const [bt, setBt] = useState<BacktestRun | null>(null);
  const [pub, setPub] = useState<PublicSettingsResp | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tooSmall, setTooSmall] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [latest, publicSettings] = await Promise.all([
          apiGet<LatestSignalResp>("/api/signal/latest"),
          apiGet<PublicSettingsResp>("/api/settings/public"),
        ]);
        if (cancelled) return;
        setSig(latest.signal);
        setPub(publicSettings);

        const d = publicSettings.backtest_defaults ?? {};
        const qs = new URLSearchParams();
        qs.set("sizing_mode", String(d.sizing_mode ?? "confidence"));
        qs.set("buy_threshold", String(d.buy_threshold ?? 0.08));
        qs.set("sell_threshold", String(d.sell_threshold ?? -0.08));
        qs.set("fee_bps", String(d.fee_bps ?? 0));
        qs.set("slippage_bps", String(d.slippage_bps ?? 0));
        qs.set("vol_window", String(d.vol_window ?? 72));
        qs.set("max_position_size", String(d.max_position_size ?? 1.0));
        qs.set("target_volatility", String(d.target_volatility ?? 0.2));
        qs.set("initial_capital", String(d.initial_capital ?? 10_000));

        const backtest = await apiGet<BacktestRun>(`/api/backtest/run?${qs.toString()}`, { timeoutMs: 180_000 });
        if (cancelled) return;
        setBt(backtest);
      } catch (e) {
        if (cancelled) return;
        setErr((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const min = 980;
    const onResize = () => setTooSmall(typeof window !== "undefined" && window.innerWidth < min);
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  if (err) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-card p-6 text-card-foreground">
        <h1 className="text-lg font-semibold">Cannot reach API</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {err}
        </p>
      </div>
    );
  }

  if (!sig || !bt || !pub) return <p className="text-muted-foreground">Loading overview…</p>;

  if (tooSmall) {
    return (
      <div className="rounded-xl border border-border bg-card p-10 text-center">
        <h1 className="text-2xl font-semibold tracking-tight text-white">Overview</h1>
        <p className="mt-3 text-sm text-muted-foreground">
          not built for small screen because I have a life and a full time job outside of this passion project
        </p>
        <p className="mt-2 text-xs text-muted-foreground">Try widening the window or zooming out.</p>
      </div>
    );
  }

  return <OverviewBody sig={sig} bt={bt} pub={pub} />;
}

type OverviewBodyProps = {
  sig: Record<string, unknown>;
  bt: BacktestRun;
  pub: PublicSettingsResp;
};

function OverviewBody({ sig, bt, pub }: OverviewBodyProps) {
  const br = (sig.breakdown as Record<string, unknown> | null) ?? {};
  const finalScore = safeFloat(sig.final_score);
  const conf = Math.min(1, Math.max(0, Math.abs(finalScore)));
  const lbl = signalLabelFromAction(String(sig.action ?? "HOLD"));

  const mlScore = safeFloat(br.ml_score);
  const sentimentScore = safeFloat(sig.news_score);
  const technicalScore = safeFloat(sig.technical_score);

  const d = pub.backtest_defaults ?? {};
  const buyTh = Number(d.buy_threshold ?? bt.params.buy_threshold ?? 0.08);
  const sellTh = Number(d.sell_threshold ?? bt.params.sell_threshold ?? -0.08);
  const feeBps = Number(d.fee_bps ?? bt.params.fee_bps ?? 0);
  const slipBps = Number(d.slippage_bps ?? bt.params.slippage_bps ?? 0);
  const sizingMode = String(d.sizing_mode ?? bt.params.sizing_mode ?? "confidence");
  const volWindow = Number(d.vol_window ?? bt.params.vol_window ?? 72);
  const maxPos = Number(d.max_position_size ?? bt.params.max_position_size ?? 1);
  const tgtVol = Number(d.target_volatility ?? bt.params.target_volatility ?? 0.2);

  const summaryNorm = useMemo(() => normalizeSummary(bt.summary), [bt.summary]);

  const equity = useMemo(() => {
    const benchByTs = new Map(bt.benchmark_curve.map((p) => [p.ts, p.equity ?? 0]));
    return downsampleRows(
      bt.equity_curve.map((p) => ({
        ts: String(p.ts).slice(0, 10),
        strategy: safeFloat(p.equity),
        benchmark: safeFloat(benchByTs.get(p.ts)),
      })),
      CHART_MAX_POINTS,
    );
  }, [bt.benchmark_curve, bt.equity_curve]);

  const drawdown = useMemo(
    () =>
      downsampleRows(
        bt.drawdown_curve.map((p) => ({
          ts: String(p.ts).slice(0, 10),
          drawdown: safeFloat(p.drawdown),
        })),
        CHART_MAX_POINTS,
      ),
    [bt.drawdown_curve],
  );

  const exposure = useMemo(
    () =>
      downsampleRows(
        bt.exposure_curve.map((p) => ({
          ts: String(p.ts).slice(0, 10),
          exposure: safeFloat(p.exposure),
        })),
        CHART_MAX_POINTS,
      ),
    [bt.exposure_curve],
  );

  const score = useMemo(
    () =>
      downsampleRows(
        (bt.score_curve ?? []).map((p) => ({
          ts: String(p.ts).slice(0, 10),
          final_score: safeFloat(p.final_score),
        })),
        CHART_MAX_POINTS,
      ),
    [bt.score_curve],
  );

  const periodDays = bt.bars > 0 ? Math.round(bt.bars / 24) : 0;
  const interpretation = useMemo(() => interpretSummary(summaryNorm), [summaryNorm]);

  return (
    <div className="max-w-full space-y-6 overflow-x-hidden">
      {/* 1) Hero Section (Current Signal) */}
      <section className="rounded-xl border border-border bg-card p-6">
        {/* w-full: flex row with a lone child was shrinking this block to content width, leaving empty space */}
        <div className="w-full min-w-0 max-w-full">
          <div className="text-xs font-semibold uppercase tracking-wide text-primary">Current signal</div>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${signalPillClass(lbl)}`}>
              {lbl}
            </span>
            <span className="text-sm text-muted-foreground">
              Updated <span className="font-mono text-foreground">{String(sig.run_at ?? "—")}</span>
            </span>
          </div>
          <div className="mt-4 grid w-full min-w-0 grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="flex min-h-[92px] min-w-0 flex-col justify-between rounded-lg border border-border/60 bg-background/30 p-4">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Final score</div>
              <div className="mt-1 font-mono text-3xl font-semibold tabular-nums text-foreground">
                {`${finalScore >= 0 ? "+" : ""}${finalScore.toFixed(3)}`}
              </div>
            </div>
            <div className="flex min-h-[92px] min-w-0 flex-col justify-between rounded-lg border border-border/60 bg-background/30 p-4">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Confidence</div>
              <div className="mt-1 font-mono text-3xl font-semibold tabular-nums text-foreground">
                {`${Math.round(conf * 100)}%`}
              </div>
            </div>
            <div className="flex min-h-[92px] min-w-0 flex-col justify-between rounded-lg border border-border/60 bg-background/30 p-4">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Breakdown</div>
              <div className="mt-2 flex min-w-0 flex-col gap-1.5 font-mono text-xs text-foreground sm:text-sm">
                <span title="ML score">
                  ML {mlScore >= 0 ? "+" : ""}
                  {mlScore.toFixed(3)}
                </span>
                <span title="News sentiment score">
                  Sentiment {sentimentScore >= 0 ? "+" : ""}
                  {sentimentScore.toFixed(3)}
                </span>
                <span title="Technical score">
                  Technical {technicalScore >= 0 ? "+" : ""}
                  {technicalScore.toFixed(3)}
                </span>
              </div>
            </div>
          </div>
          <p className="mt-3 text-sm text-muted-foreground">
            Signal is generated by blending ML prediction, news sentiment, and technical indicators.
          </p>
        </div>
      </section>

      {/* 2) Strategy Explanation */}
      <section className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">Strategy explanation</h2>
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-border/60 bg-background/30 p-4 text-sm text-muted-foreground">
            <div className="font-semibold text-foreground">Strategy logic</div>
            <div className="mt-2 space-y-1">
              <div>
                If score {">"} <span className="font-mono text-foreground">{buyTh}</span> → <strong className="text-foreground">Long</strong>
              </div>
              <div>
                If score {"<"} <span className="font-mono text-foreground">{sellTh}</span> → <strong className="text-foreground">Short</strong>
              </div>
              <div>Else → <strong className="text-foreground">Flat</strong></div>
            </div>
          </div>
          <div className="rounded-lg border border-border/60 bg-background/30 p-4 text-sm text-muted-foreground">
            <div className="font-semibold text-foreground">Execution, costs, sizing</div>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Execution</div>
                <div className="mt-1">Next bar (t → t+1)</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Sizing</div>
                <div className="mt-1 font-mono text-foreground">{sizingMode}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Fee</div>
                <div className="mt-1 font-mono text-foreground">{feeBps} bps</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Slippage</div>
                <div className="mt-1 font-mono text-foreground">{slipBps} bps</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 3) Headline Performance Metrics */}
      <section className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">Headline performance</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <MetricCard k="Cumulative return" v={fmtPct(summaryNorm.cumulative_return)} tip="Total return over the tested period." />
          <MetricCard k="Sharpe ratio" v={fmtNum(summaryNorm.sharpe)} tip="Risk-adjusted return (higher is better)." />
          <MetricCard k="Max drawdown" v={fmtPct(summaryNorm.max_drawdown)} tip="Worst peak-to-trough loss." />
          <MetricCard k="Win rate" v={fmtPct(summaryNorm.win_rate)} tip="Share of profitable trades." />
          <MetricCard k="Trades" v={String(summaryNorm.trade_count)} tip="Number of simulated trades." />
          <MetricCard k="Alpha vs BTC" v={fmtPct(summaryNorm.alpha_vs_benchmark)} tip="Return difference vs buy-and-hold BTC." />
        </div>
      </section>

      {/* 4) Equity Curve (main chart) */}
      <section className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">Equity curve</h2>
        <div className="mt-3 h-[360px]">
          <ClientOnly>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={equity}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="ts" stroke="var(--muted-foreground)" fontSize={11} tickMargin={8} />
                <YAxis stroke="var(--muted-foreground)" fontSize={11} tickMargin={8} />
                <Tooltip content={<TooltipBox />} />
                <Line name="Strategy" type="monotone" dataKey="strategy" stroke="#10b981" dot={false} strokeWidth={2} />
                <Line name="BTC buy-and-hold" type="monotone" dataKey="benchmark" stroke="var(--muted-foreground)" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </ClientOnly>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">Strategy performance vs BTC buy-and-hold</p>
      </section>

      {/* 5) Drawdown Chart */}
      <section className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">Drawdown</h2>
        <div className="mt-3 h-56">
          <ClientOnly>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={drawdown}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="ts" stroke="var(--muted-foreground)" fontSize={11} tickMargin={8} />
                <YAxis stroke="var(--muted-foreground)" fontSize={11} tickMargin={8} domain={["dataMin", 0]} />
                <Tooltip content={<TooltipBox />} />
                <Line name="Drawdown" type="monotone" dataKey="drawdown" stroke="#ef4444" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </ClientOnly>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">Peak-to-trough losses over time</p>
      </section>

      {/* 6) Position / Exposure Chart */}
      <section className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">Exposure</h2>
        <div className="mt-3 h-56">
          <ClientOnly>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={exposure}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="ts" stroke="var(--muted-foreground)" fontSize={11} tickMargin={8} />
                <YAxis
                  type="number"
                  stroke="var(--muted-foreground)"
                  fontSize={11}
                  tickMargin={8}
                  domain={[-1, 1]}
                  ticks={[-1, -0.5, 0, 0.5, 1]}
                  allowDataOverflow
                />
                <Tooltip content={<TooltipBox />} />
                <ReferenceLine y={0} stroke="var(--border)" />
                <Line name="Exposure" type="stepAfter" dataKey="exposure" stroke="#60a5fa" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </ClientOnly>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Strategy exposure over time (downsampled to ~{CHART_MAX_POINTS} points for readability)
        </p>
      </section>

      {/* 7) Signal Over Time Chart */}
      <section className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">Signal strength</h2>
        <div className="mt-3 h-56">
          <ClientOnly>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={score} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="ts" stroke="var(--muted-foreground)" fontSize={11} tickMargin={8} />
                <YAxis
                  type="number"
                  stroke="var(--muted-foreground)"
                  fontSize={11}
                  tickMargin={8}
                  domain={[-1.05, 1.05]}
                  ticks={[-1, -0.5, 0, 0.5, 1]}
                  allowDataOverflow
                />
                <Tooltip content={<TooltipBox />} />
                <ReferenceLine y={Number(buyTh)} stroke="#10b981" strokeDasharray="4 4" />
                <ReferenceLine y={Number(sellTh)} stroke="#ef4444" strokeDasharray="4 4" />
                <ReferenceLine y={0} stroke="var(--border)" />
                <Line
                  name="Final score"
                  type="monotone"
                  dataKey="final_score"
                  stroke="#f59e0b"
                  dot={false}
                  strokeWidth={2}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </ClientOnly>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Signal strength over time (score is −1 to +1; downsampled to ~{CHART_MAX_POINTS} points)
        </p>
      </section>

      {/* 8) Backtest Settings Panel */}
      <section className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">Backtest settings</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <SettingRow k="Period" v={periodDays ? `~${periodDays} days (1h bars)` : `${bt.bars} bars`} />
          <SettingRow k="Sizing mode" v={sizingMode} mono />
          <SettingRow k="Fee" v={`${feeBps} bps`} mono />
          <SettingRow k="Slippage" v={`${slipBps} bps`} mono />
          <SettingRow k="Volatility window" v={`${volWindow} bars`} mono />
          <SettingRow k="Max position size" v={`${maxPos}`} mono />
          <SettingRow k="Buy threshold" v={`${buyTh}`} mono />
          <SettingRow k="Sell threshold" v={`${sellTh}`} mono />
          <SettingRow k="Target volatility" v={`${tgtVol}`} mono />
          <SettingRow k="Dataset source" v={bt.dataset_source} mono />
        </div>
      </section>

      {/* 9) Summary / Interpretation */}
      <section className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">Summary</h2>
        <div className="mt-3 max-w-3xl space-y-2 text-sm text-muted-foreground">
          {interpretation.length ? (
            <ul className="list-disc pl-5">
              {interpretation.map((t, idx) => (
                <li key={`${bt.bars}-${idx}-${summaryNorm.alpha_vs_benchmark}-${summaryNorm.sharpe}-${summaryNorm.max_drawdown}`}>
                  {t}
                </li>
              ))}
            </ul>
          ) : (
            <p>Not enough data to generate an interpretation yet.</p>
          )}
          <p className="text-xs">
            Trust check: backtests use next-bar execution (t → t+1), apply fees/slippage on turnover, and avoid lookahead
            by construction.
          </p>
        </div>
      </section>
    </div>
  );
}

function MetricCard({ k, v, tip }: { k: string; v: string; tip?: string }) {
  return (
    <div className="rounded-lg border border-border/80 bg-background/40 px-3 py-2" title={tip}>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{k}</div>
      <div className="mt-0.5 font-mono text-lg text-foreground">{v}</div>
    </div>
  );
}

function SettingRow({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="rounded-lg border border-border/80 bg-background/40 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{k}</div>
      <div className={`mt-0.5 text-sm text-foreground ${mono ? "font-mono" : ""}`}>{v}</div>
    </div>
  );
}
