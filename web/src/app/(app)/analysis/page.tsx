"use client";

import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { ClientOnly } from "@/components/client-only";
import { apiGet } from "@/lib/api";

type Candle = { ts: number | string; open: number; high: number; low: number; close: number };
type Article = Record<string, unknown>;

type MarketPayload = {
  signals: Record<string, unknown>[];
  candles_1h: Candle[];
  candles_4h: Candle[];
  news: Article[];
};

function candleRows(rows: Candle[], label: string) {
  if (!rows.length) {
    return <p className="text-sm text-muted-foreground">{label}: no rows.</p>;
  }
  const data = rows.map((c) => ({
    t:
      typeof c.ts === "number"
        ? new Date(c.ts * 1000).toISOString().slice(0, 16).replace("T", " ")
        : String(c.ts),
    close: Number(c.close),
  }));
  return (
    <div className="h-72">
      <p className="mb-2 text-xs font-medium text-muted-foreground">{label}</p>
      <ClientOnly>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis dataKey="t" tick={{ fontSize: 8 }} interval="preserveStartEnd" />
            <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10 }} />
            <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)" }} />
            <Line type="monotone" dataKey="close" stroke="#fbbf24" dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </ClientOnly>
    </div>
  );
}

function actionColor(a: string) {
  const u = a.toUpperCase();
  if (u === "BUY") return "#22c55e";
  if (u === "SELL") return "#ef4444";
  return "#94a3b8";
}

export default function MarketAnalysisPage() {
  const [tab, setTab] = useState<"signals" | "candles" | "news">("signals");
  const [sigLimit, setSigLimit] = useState(120);
  const [candleBars, setCandleBars] = useState(200);
  const [data, setData] = useState<MarketPayload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    apiGet<MarketPayload>(
      `/api/market/analysis?sig_limit=${sigLimit}&candle_bars=${candleBars}&news_limit=400`,
    )
      .then(setData)
      .catch((e: Error) => setErr(e.message));
  }, [sigLimit, candleBars]);

  if (err) {
    return <p className="text-destructive">{err}</p>;
  }
  if (!data) {
    return <p className="text-muted-foreground">Loading market analysis…</p>;
  }

  const sigData = data.signals.map((s) => {
    const raw = s as Record<string, unknown>;
    return {
      run_at: String(raw.run_at ?? ""),
      btc: Number(raw.btc_price),
      final: Number(raw.final_score),
      news: Number(raw.news_score),
      tech: Number(raw.technical_score),
      action: String(raw.action ?? ""),
    };
  });

  const actionScatter = sigData.map((s) => ({
    x: s.run_at,
    y: s.btc,
    z: 80,
    fill: actionColor(s.action),
    action: s.action,
    final: s.final,
  }));

  return (
    <div>
      <div className="mb-6 rounded-xl border border-border bg-card p-6">
        <h1 className="text-2xl font-semibold tracking-tight">Market analysis</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Signal history, stored OHLC, and news sentiment from your local DB — for context, not predictions.
        </p>
        <div className="mt-4 flex flex-wrap gap-4 text-sm">
          <label className="flex items-center gap-2">
            <span className="text-muted-foreground">Signals</span>
            <input
              type="number"
              min={20}
              max={500}
              step={10}
              value={sigLimit}
              onChange={(e) => setSigLimit(Number(e.target.value))}
              className="w-20 rounded border border-border bg-background px-2 py-1 font-mono text-xs"
            />
          </label>
          <label className="flex items-center gap-2">
            <span className="text-muted-foreground">Candles / TF</span>
            <input
              type="number"
              min={50}
              max={500}
              step={10}
              value={candleBars}
              onChange={(e) => setCandleBars(Number(e.target.value))}
              className="w-20 rounded border border-border bg-background px-2 py-1 font-mono text-xs"
            />
          </label>
        </div>
      </div>

      <div className="mb-4 flex gap-2 border-b border-border pb-2">
        {(["signals", "candles", "news"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`rounded-md px-3 py-1.5 text-sm capitalize ${
              tab === t ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
            }`}
          >
            {t === "signals" ? "Signals & scores" : t === "candles" ? "Stored candles" : "News pulse"}
          </button>
        ))}
      </div>

      {tab === "signals" && (
        <div>
          {!sigData.length ? (
            <p className="text-muted-foreground">No signals yet — run btc-paper-run.</p>
          ) : (
            <>
              <div className="h-72">
                <p className="mb-2 text-sm font-medium">BTC at each run & scores</p>
                <ClientOnly>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={sigData}>
                      <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                      <XAxis dataKey="run_at" tick={{ fontSize: 8 }} interval="preserveStartEnd" />
                      <YAxis yAxisId="l" domain={["auto", "auto"]} tick={{ fontSize: 10 }} />
                      <YAxis
                        yAxisId="r"
                        orientation="right"
                        domain={[-1.05, 1.05]}
                        tick={{ fontSize: 10 }}
                      />
                      <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)" }} />
                      <Line yAxisId="l" type="monotone" dataKey="btc" stroke="#fbbf24" dot name="BTC" />
                      <Line yAxisId="r" type="monotone" dataKey="final" stroke="#38bdf8" dot={false} name="final" />
                      <Line
                        yAxisId="r"
                        type="monotone"
                        dataKey="news"
                        stroke="#a78bfa"
                        dot={false}
                        strokeDasharray="4 4"
                        name="news"
                      />
                      <Line
                        yAxisId="r"
                        type="monotone"
                        dataKey="tech"
                        stroke="#34d399"
                        dot={false}
                        strokeDasharray="4 4"
                        name="tech"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ClientOnly>
              </div>
              <div className="mt-8 h-64">
                <p className="mb-2 text-sm font-medium">Actions vs BTC (marker color)</p>
                <ClientOnly>
                  <ResponsiveContainer width="100%" height="100%">
                    <ScatterChart>
                      <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                      <XAxis dataKey="x" name="run" tick={{ fontSize: 8 }} />
                      <YAxis dataKey="y" name="BTC" tick={{ fontSize: 10 }} domain={["auto", "auto"]} />
                      <ZAxis dataKey="z" range={[60, 60]} />
                      <Tooltip
                        cursor={{ strokeDasharray: "3 3" }}
                        content={({ active, payload }) => {
                          if (!active || !payload?.[0]) {
                            return null;
                          }
                          const p = payload[0].payload as { x: string; y: number; action: string; final: number };
                          return (
                            <div className="rounded border border-border bg-card p-2 text-xs shadow-md">
                              <div>{p.action}</div>
                              <div>BTC {p.y.toFixed(0)}</div>
                              <div>final {p.final.toFixed(3)}</div>
                              <div className="text-muted-foreground">{p.x}</div>
                            </div>
                          );
                        }}
                      />
                      <Scatter data={actionScatter} fill="#8884d8">
                        {actionScatter.map((e, i) => (
                          <Cell key={i} fill={e.fill} />
                        ))}
                      </Scatter>
                    </ScatterChart>
                  </ResponsiveContainer>
                </ClientOnly>
              </div>
              <div className="mt-6 overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-left text-xs">
                  <thead className="bg-muted">
                    <tr>
                      <th className="p-2">run_at</th>
                      <th className="p-2">action</th>
                      <th className="p-2">btc</th>
                      <th className="p-2">final</th>
                      <th className="p-2">news</th>
                      <th className="p-2">tech</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...sigData].reverse().slice(0, 40).map((s) => (
                      <tr key={s.run_at} className="border-t border-border">
                        <td className="p-2 font-mono">{s.run_at}</td>
                        <td className="p-2">{s.action}</td>
                        <td className="p-2 font-mono">{s.btc.toFixed(0)}</td>
                        <td className="p-2 font-mono">{s.final.toFixed(3)}</td>
                        <td className="p-2 font-mono">{s.news.toFixed(3)}</td>
                        <td className="p-2 font-mono">{s.tech.toFixed(3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {tab === "candles" && (
        <div className="space-y-8">
          {candleRows(data.candles_4h, "4h (CoinGecko OHLC)")}
          {candleRows(data.candles_1h, "1h (market chart)")}
          <p className="text-xs text-muted-foreground">
            Each pipeline run replaces stored candles for that timeframe — not full exchange history.
          </p>
        </div>
      )}

      {tab === "news" && (
        <div>
          {!data.news.length ? (
            <p className="text-muted-foreground">No news rows.</p>
          ) : (
            <ul className="space-y-2">
              {data.news.slice(0, 80).map((a) => (
                <li key={String(a.id)} className="rounded border border-border bg-card p-3 text-sm">
                  <div className="font-medium">{String(a.headline ?? "")}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    score {Number(a.sentiment_score ?? 0).toFixed(2)} · {String(a.published_at ?? a.scraped_at ?? "")}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
