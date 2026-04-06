"use client";

import { useEffect, useState } from "react";
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
import { apiGet } from "@/lib/api";

type Ta = {
  timeframe: string;
  score: number;
  trend: number;
  rsi: number;
  rsi_signal: number;
  bollinger_signal: number;
  macd_signal: number;
  volatility_high: boolean;
  detail: Record<string, unknown>;
} | null;

type LiveTech = {
  spot_usd: number | null;
  spot_error: string | null;
  spot_source: string | null;
  err_1h: string | null;
  err_4h: string | null;
  ta_1h: Ta;
  ta_4h: Ta;
  weight_1h: number;
  weight_4h: number;
  technical_score: number | null;
  blend_explanation: string;
  chart_1h: { ts: string; close: number }[];
  chart_4h: { ts: string; close: number }[];
};

function TaTable({ ta, title }: { ta: NonNullable<Ta>; title: string }) {
  const mr0 = ta.rsi_signal + ta.bollinger_signal;
  const mr1 = ta.volatility_high ? mr0 * 0.5 : mr0;
  const raw = ta.trend + mr1 + ta.macd_signal;
  const clipped = Math.max(-1, Math.min(1, raw / 2.5));
  const rows = [
    { code: "trend", meaning: "Bull (+1) / bear (−1) EMA stack vs close", value: `${ta.trend >= 0 ? "+" : ""}${ta.trend}` },
    { code: "rsi_s", meaning: "RSI mean-reversion bump", value: ta.rsi_signal.toFixed(2) },
    { code: "bb_s", meaning: "Bollinger bump", value: ta.bollinger_signal.toFixed(2) },
    { code: "mean_rev", meaning: "rsi_s + bb_s, ×0.5 if vol high", value: `${mr0.toFixed(2)} → ${mr1.toFixed(2)}` },
    { code: "macd_s", meaning: "MACD vs signal", value: ta.macd_signal.toFixed(2) },
    { code: "raw", meaning: "trend + mean_rev + macd_s", value: raw.toFixed(4) },
    { code: "score", meaning: "clip(raw ÷ 2.5)", value: clipped.toFixed(4) },
  ];
  return (
    <details className="mt-3 rounded-lg border border-border bg-card">
      <summary className="cursor-pointer p-3 text-sm font-medium">Step-by-step score: {title}</summary>
      <div className="overflow-x-auto border-t border-border p-3">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="text-muted-foreground">
              <th className="py-1 pr-2">Code</th>
              <th className="py-1 pr-2">Meaning</th>
              <th className="py-1">Value</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.code} className="border-t border-border/60">
                <td className="py-1.5 pr-2 font-mono">{r.code}</td>
                <td className="py-1.5 pr-2 text-muted-foreground">{r.meaning}</td>
                <td className="py-1.5 font-mono">{r.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export default function TechnicalPage() {
  const [data, setData] = useState<LiveTech | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    apiGet<LiveTech>("/api/technical/live?chart_points=200", { timeoutMs: 120_000 })
      .then(setData)
      .catch((e: Error) => setErr(e.message));
  }, []);

  if (err) {
    return (
      <div className="max-w-xl space-y-2">
        <p className="text-destructive">{err}</p>
        <p className="text-sm text-muted-foreground">
          From the repo root run <code className="rounded bg-muted px-1">btc-paper-api</code> (after{" "}
          <code className="rounded bg-muted px-1">pip install -e &apos;.[api]&apos;</code>). This page calls CoinGecko
          twice; first load can take 30–90s.
        </p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="max-w-xl space-y-2 text-muted-foreground">
        <p>Loading live technicals…</p>
        <p className="text-sm">
          Fetching CoinGecko market data on the server — can take up to ~2 minutes on a cold start or rate limits.
          Ensure <code className="rounded bg-muted px-1 text-foreground">btc-paper-api</code> is running on{" "}
          <code className="rounded bg-muted px-1 text-foreground">127.0.0.1:8000</code>.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6 rounded-xl border border-border bg-card p-6">
        <h1 className="text-2xl font-semibold tracking-tight">Technical</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Live CoinGecko series with the same indicator stack as the pipeline. Normalized score is about −1 … +1
          per timeframe; weights {data.weight_1h} (1h) + {data.weight_4h} (4h) blend into one technical score when
          both sides are available.
        </p>
        {data.spot_usd != null ? (
          <p className="mt-3 font-mono text-lg font-semibold text-amber-500">
            ${data.spot_usd.toLocaleString(undefined, { maximumFractionDigits: 2 })}{" "}
            <span className="text-xs font-normal text-muted-foreground">({data.spot_source})</span>
          </p>
        ) : (
          <p className="mt-3 text-sm text-muted-foreground">Spot: unavailable ({data.spot_error ?? "error"})</p>
        )}
        <p className="mt-2 text-sm text-muted-foreground">
          Blended technical score:{" "}
          <strong className="text-foreground">
            {data.technical_score != null ? data.technical_score.toFixed(4) : "—"}
          </strong>
          . {data.blend_explanation}
        </p>
        <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
          Charts plot <strong className="text-foreground">live CoinGecko closes</strong> (not simulated). RSI, MACD,
          and Bollinger drive the bot via the same code as the pipeline; here you see{" "}
          <strong className="text-foreground">price lines only</strong>. Open{" "}
          <strong className="text-foreground">Step-by-step score</strong> below for{" "}
          <span className="font-mono text-foreground">rsi_s</span>,{" "}
          <span className="font-mono text-foreground">bb_s</span>,{" "}
          <span className="font-mono text-foreground">macd_s</span> (score bumps) and the last-bar{" "}
          <span className="font-mono text-foreground">RSI(14)</span> in the API field{" "}
          <span className="font-mono text-foreground">ta_*.rsi</span>. Full multi-panel indicator charts can be added
          later by returning series from the API and plotting in Recharts.
        </p>
        {(data.err_1h || data.err_4h) && (
          <p className="mt-2 text-xs text-destructive">
            {data.err_1h ? `1h: ${data.err_1h} ` : ""}
            {data.err_4h ? `4h: ${data.err_4h}` : ""}
          </p>
        )}
      </div>

      <div className="grid gap-8 lg:grid-cols-2">
        <section>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">1h (market chart)</h2>
          {data.chart_1h.length ? (
            <div className="mt-2 h-56">
              <ClientOnly>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.chart_1h}>
                    <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                    <XAxis dataKey="ts" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
                    <YAxis tick={{ fontSize: 10 }} domain={["auto", "auto"]} />
                    <Tooltip
                      contentStyle={{ background: "var(--card)", border: "1px solid var(--border)" }}
                      labelFormatter={(l) => String(l)}
                    />
                    <Line type="monotone" dataKey="close" stroke="var(--chart-1)" dot={false} strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </ClientOnly>
            </div>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">No 1h series.</p>
          )}
          {data.ta_1h ? <TaTable ta={data.ta_1h} title="1h" /> : null}
        </section>
        <section>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">4h (OHLC)</h2>
          {data.chart_4h.length ? (
            <div className="mt-2 h-56">
              <ClientOnly>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.chart_4h}>
                    <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                    <XAxis dataKey="ts" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
                    <YAxis tick={{ fontSize: 10 }} domain={["auto", "auto"]} />
                    <Tooltip
                      contentStyle={{ background: "var(--card)", border: "1px solid var(--border)" }}
                      labelFormatter={(l) => String(l)}
                    />
                    <Line type="monotone" dataKey="close" stroke="var(--chart-2)" dot={false} strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </ClientOnly>
            </div>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">No 4h series.</p>
          )}
          {data.ta_4h ? <TaTable ta={data.ta_4h} title="4h" /> : null}
        </section>
      </div>
    </div>
  );
}
