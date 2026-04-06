"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ClientOnly } from "@/components/client-only";
import { ScoreBar } from "@/components/score-bar";
import { apiGet } from "@/lib/api";

type Overview = {
  live_price: number | null;
  price_warn: string;
  signal: Record<string, unknown> | null;
  news: Record<string, unknown>[];
  open_trade: Record<string, unknown> | null;
  performance: { trade_count: number; wins: number; total_pnl: number };
  max_drawdown_usd: number;
  win_rate_pct: number;
  cumulative_pnl: { i: number; v: number }[];
  settings: Record<string, number | boolean | string>;
};

function safeFloat(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function fmtSigned2(n: number) {
  const s = n.toFixed(2);
  return n >= 0 ? `+${s}` : s;
}

function actionPillClass(action: string): string {
  const a = (action || "HOLD").toUpperCase();
  if (a === "BUY") return "bg-emerald-600 text-white";
  if (a === "SELL") return "bg-red-600 text-white";
  return "border border-border bg-muted text-muted-foreground";
}

function blendDesc(s: Record<string, number | boolean | string>, mlActive: boolean) {
  const nw = safeFloat(s.news_weight);
  const tw = safeFloat(s.technical_weight);
  const mw = safeFloat(s.ml_weight);
  const ln = safeFloat(s.legacy_news_weight);
  const lt = safeFloat(s.legacy_technical_weight);
  if (mlActive) {
    return ` + ML (${(nw * 100).toFixed(0)}% / ${(tw * 100).toFixed(0)}% / ${(mw * 100).toFixed(0)}%)`;
  }
  return ` (${(ln * 100).toFixed(0)}% news / ${(lt * 100).toFixed(0)}% technical — ML off or no models)`;
}

export default function OverviewPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Overview>("/api/overview")
      .then(setData)
      .catch((e: Error) => setErr(e.message));
  }, []);

  if (err) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-card p-6 text-card-foreground">
        <h1 className="text-lg font-semibold">Cannot reach API</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {err}. From the repo root run{" "}
          <code className="rounded bg-muted px-1">pip install -e &apos;.[api]&apos;</code> then{" "}
          <code className="rounded bg-muted px-1">btc-paper-api</code> (default{" "}
          <code className="rounded bg-muted px-1">127.0.0.1:8000</code>). Set{" "}
          Remove <code className="rounded bg-muted px-1">NEXT_PUBLIC_API_URL</code> from{" "}
          <code className="rounded bg-muted px-1">web/.env.local</code> so requests use the built-in /api proxy, or
          set <code className="rounded bg-muted px-1">API_PROXY_TARGET</code> if FastAPI is not on 127.0.0.1:8000.
        </p>
      </div>
    );
  }

  if (!data) {
    return <p className="text-muted-foreground">Loading overview…</p>;
  }

  const { signal, settings } = data;
  const perf = data.performance;

  const navRow = (
    <p className="mt-4 text-sm text-muted-foreground">
      Dig deeper:{" "}
      <Link className="text-primary underline-offset-4 hover:underline" href="/news">
        News
      </Link>
      {" · "}
      <Link className="text-primary underline-offset-4 hover:underline" href="/technical">
        Technical
      </Link>
      {" · "}
      <Link className="text-primary underline-offset-4 hover:underline" href="/paper-trading">
        Paper trading
      </Link>
      {" · "}
      <Link className="text-primary underline-offset-4 hover:underline" href="/trades">
        Trade history
      </Link>
      {" · "}
      <Link className="text-primary underline-offset-4 hover:underline" href="/analysis">
        Market analysis
      </Link>
      {" · "}
      <Link className="text-primary underline-offset-4 hover:underline" href="/ml">
        ML
      </Link>
    </p>
  );

  if (!signal) {
    return (
      <div>
        <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
          <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Your command center for BTC paper trading and model signals. Run the pipeline once to unlock
            scores, rationale, and a full snapshot.
          </p>
          <div className="mt-4 rounded-lg border border-dashed border-primary/40 bg-muted/30 p-4 text-sm">
            <strong>No signal in the database yet.</strong> From the project root run{" "}
            <code className="rounded bg-muted px-1">btc-paper-run</code> (after{" "}
            <code className="rounded bg-muted px-1">pip install -e .</code>). You can still read{" "}
            <Link href="/news" className="text-primary underline-offset-4 hover:underline">
              News
            </Link>{" "}
            and use{" "}
            <Link href="/paper-trading" className="text-primary underline-offset-4 hover:underline">
              Paper trading
            </Link>{" "}
            manually.
          </div>
          {data.price_warn ? (
            <p className="mt-2 text-xs text-muted-foreground">Live price: {data.price_warn}</p>
          ) : null}
        </div>
        {navRow}
        <div className="mt-8 grid grid-cols-2 gap-4 md:grid-cols-4">
          <Metric label="Closed trades" value={String(perf.trade_count)} />
          <Metric label="Total PnL ($)" value={safeFloat(perf.total_pnl).toFixed(2)} />
          <Metric label="Win rate" value={`${data.win_rate_pct.toFixed(1)}%`} />
          <Metric label="Max drawdown ($)" value={data.max_drawdown_usd.toFixed(2)} />
        </div>
        {data.open_trade ? (
          <p className="mt-4 text-sm text-muted-foreground">
            Open paper position — see{" "}
            <Link href="/paper-trading" className="text-primary underline-offset-4 hover:underline">
              Paper trading
            </Link>
            .
          </p>
        ) : null}
        {data.news.length > 0 ? (
          <div className="mt-8">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">Latest headlines</h2>
            <ul className="mt-3 space-y-2">
              {data.news.slice(0, 5).map((row) => (
                <li
                  key={String(row.id ?? row.url)}
                  className="rounded-md border border-border bg-card p-3 text-sm"
                >
                  <span className="font-medium text-card-foreground">{String(row.headline ?? "")}</span>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {String(row.sentiment_label ?? "—")} ({fmtSigned2(safeFloat(row.sentiment_score))}) · impact{" "}
                    {String(row.impact ?? "—")}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {data.cumulative_pnl.length > 1 ? (
          <div className="mt-8 h-64">
            <h2 className="mb-2 text-sm font-semibold">Cumulative realized PnL</h2>
            <ClientOnly>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data.cumulative_pnl}>
                  <XAxis dataKey="i" hide />
                  <YAxis stroke="var(--muted-foreground)" fontSize={11} />
                  <Tooltip
                    contentStyle={{
                      background: "var(--card)",
                      border: "1px solid var(--border)",
                    }}
                  />
                  <Line type="monotone" dataKey="v" stroke="var(--primary)" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </ClientOnly>
          </div>
        ) : null}
      </div>
    );
  }

  const br = (signal.breakdown as Record<string, unknown> | null) ?? {};
  const mlBlock = (br.ml as Record<string, unknown> | undefined) ?? {};
  const weightsMeta = (br.weights as Record<string, unknown> | undefined) ?? {};
  const mlActive = Boolean(weightsMeta.ml_active);
  const tech = (br.technical as Record<string, unknown> | undefined) ?? {};
  const t1h = (tech["1h"] as Record<string, unknown> | undefined) ?? {};
  const t4h = (tech["4h"] as Record<string, unknown> | undefined) ?? {};

  const priceDisp =
    data.live_price != null ? data.live_price : safeFloat(signal.btc_price);
  const action = String(signal.action);
  const conf = safeFloat(signal.confidence);
  const newsS = safeFloat(signal.news_score);
  const techS = safeFloat(signal.technical_score);
  const finalS = safeFloat(signal.final_score);
  const mlS = safeFloat(br.ml_score);

  const hp = (mlBlock.horizon_predictions as Record<string, Record<string, unknown>> | undefined) ?? {};

  return (
    <div>
      <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
        <h1 className="text-2xl font-semibold tracking-tight">At a glance</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Latest pipeline run — sentiment + technicals{blendDesc(settings, mlActive)}.
        </p>
        <div className="mt-6 flex flex-wrap gap-8">
          <div>
            <div className="text-[10px] font-normal uppercase tracking-widest text-primary">Bitcoin</div>
            <div className="mt-1 text-3xl font-bold tabular-nums text-amber-500">
              ${priceDisp.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
            <div className="text-xs text-muted-foreground">
              {data.live_price != null ? "Live quote" : "Price at last signal"}
            </div>
          </div>
          <div>
            <div className="text-[10px] font-normal uppercase tracking-widest text-primary">Verdict</div>
            <div className="mt-2">
              <span
                className={`inline-block rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${actionPillClass(action)}`}
              >
                {action}
              </span>
            </div>
            <div className="mt-2 text-xs text-muted-foreground">
              Confidence <strong className="text-foreground">{conf.toFixed(2)}</strong> · UTC{" "}
              <code className="text-foreground">{String(signal.run_at)}</code>
            </div>
          </div>
        </div>
        {data.price_warn ? (
          <p className="mt-4 text-xs text-muted-foreground">
            Live CoinGecko fetch failed — showing signal-time price. ({data.price_warn})
          </p>
        ) : null}
      </div>

      {navRow}

      <h2 className="mt-10 text-sm font-semibold uppercase tracking-wide text-primary">Scores (−1 … +1)</h2>
      <div className="mt-3 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <ScoreCard title="News" value={newsS} />
        <ScoreCard title="Technical" value={techS} />
        <ScoreCard title="ML" value={mlS} />
        <ScoreCard title="Final (unified)" value={finalS} />
      </div>

      {Object.keys(mlBlock).length > 0 ? (
        <div className="mt-8">
          <h3 className="text-sm font-semibold">Horizon probabilities (latest)</h3>
          <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-5">
            <MiniMetric
              label="P(up) 1h"
              value={safeFloat((hp.target_up_1h as { prob_up?: unknown } | undefined)?.prob_up ?? 0.5).toFixed(3)}
            />
            <MiniMetric
              label="P(up) 12h"
              value={safeFloat((hp.target_up_12h as { prob_up?: unknown } | undefined)?.prob_up ?? 0.5).toFixed(3)}
            />
            <MiniMetric
              label="P(up) 24h"
              value={safeFloat((hp.target_up_24h as { prob_up?: unknown } | undefined)?.prob_up ?? 0.5).toFixed(3)}
            />
            <MiniMetric
              label="Blended ML prob"
              value={safeFloat(mlBlock.ml_prob ?? 0.5).toFixed(3)}
            />
            <MiniMetric label="ML bias" value={String(mlBlock.ml_bias ?? "neutral")} />
          </div>
        </div>
      ) : null}

      <h2 className="mt-10 text-sm font-semibold uppercase tracking-wide text-primary">Technical snapshot</h2>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <TfCard label="1h" d={t1h} />
        <TfCard label="4h" d={t4h} />
      </div>

      <div className="mt-10 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Metric label="Closed trades" value={String(perf.trade_count)} />
        <Metric label="Total PnL ($)" value={safeFloat(perf.total_pnl).toFixed(2)} />
        <Metric label="Win rate" value={`${data.win_rate_pct.toFixed(1)}%`} />
        <Metric label="Max drawdown ($)" value={data.max_drawdown_usd.toFixed(2)} />
      </div>

      {data.open_trade ? (
        <p className="mt-4 text-sm text-muted-foreground">
          Open paper: <strong>{String(data.open_trade.side)}</strong> @ $
          {safeFloat(data.open_trade.entry_price).toFixed(2)} —{" "}
          <Link href="/paper-trading" className="text-primary underline-offset-4 hover:underline">
            Paper trading
          </Link>
        </p>
      ) : null}

      {data.news.length > 0 ? (
        <div className="mt-10">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">Latest headlines</h2>
          <ul className="mt-3 space-y-2">
            {data.news.map((row) => (
              <li
                key={String(row.id ?? row.url)}
                className="rounded-md border border-border bg-card p-3 text-sm"
              >
                <span className="font-medium">{String(row.headline ?? "")}</span>
                <div className="mt-1 text-xs text-muted-foreground">
                  {String(row.sentiment_label ?? "—")} ({fmtSigned2(safeFloat(row.sentiment_score))})
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {data.cumulative_pnl.length > 1 ? (
        <div className="mt-10 h-64">
          <h2 className="mb-2 text-sm font-semibold">Cumulative realized PnL</h2>
          <ClientOnly>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.cumulative_pnl}>
                <XAxis dataKey="i" hide />
                <YAxis stroke="var(--muted-foreground)" fontSize={11} />
                <Tooltip
                  contentStyle={{
                    background: "var(--card)",
                    border: "1px solid var(--border)",
                  }}
                />
                <Line type="monotone" dataKey="v" stroke="var(--primary)" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </ClientOnly>
        </div>
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="text-xs uppercase tracking-wide text-primary">{label}</div>
      <div className="mt-1 text-xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono text-sm font-semibold">{value}</div>
    </div>
  );
}

function ScoreCard({ title, value }: { title: string; value: number }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h3 className="text-[11px] font-normal uppercase tracking-wide text-primary">{title}</h3>
      <div className="mt-2 font-mono text-xl font-bold tabular-nums">
        {`${value >= 0 ? "+" : ""}${value.toFixed(3)}`}
      </div>
      <ScoreBar score={value} />
      <div className="mt-2 text-xs text-muted-foreground">Scale −1 (bearish) → +1 (bullish)</div>
    </div>
  );
}

function TfCard({ label, d }: { label: string; d: Record<string, unknown> }) {
  if (!d || d.close == null) {
    return (
      <div className="rounded-lg border border-border bg-muted/20 p-4 text-sm text-muted-foreground">
        {label}: <em>No breakdown for this run.</em>
      </div>
    );
  }
  const cl = safeFloat(d.close);
  const rsi = d.rsi14 ?? "—";
  const ns = d.normalized_score != null ? safeFloat(d.normalized_score) : null;
  const trend = d.trend_term ?? "—";
  const vol = d.volatility_high ? "Yes" : "No";
  const lo = d.bb_lower;
  const hi = d.bb_upper;
  let bb = "";
  if (lo != null && hi != null) {
    bb = ` · BB ${safeFloat(lo).toFixed(0)}–${safeFloat(hi).toFixed(0)}`;
  }
  return (
    <div className="rounded-lg border border-border bg-card p-4 text-sm leading-relaxed text-muted-foreground">
      <strong className="text-foreground">{label}</strong> · close{" "}
      <strong className="text-foreground">{cl.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong> · RSI(14){" "}
      <strong className="text-foreground">{String(rsi)}</strong> · norm{" "}
      <strong className="text-foreground">{ns != null ? `${ns >= 0 ? "+" : ""}${ns.toFixed(3)}` : "—"}</strong>
      <br />
      Trend <strong className="text-foreground">{String(trend)}</strong> · vol spike{" "}
      <strong className="text-foreground">{vol}</strong>
      {bb}
    </div>
  );
}
