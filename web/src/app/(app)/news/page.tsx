"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import AnimatedDownloadButton from "@/components/ui/download-hover-button";
import { ClientOnly } from "@/components/client-only";
import { apiGet, apiPost } from "@/lib/api";

type Article = Record<string, unknown>;

type SyncResult = {
  ok: boolean;
  raw_article_count: number;
  scored_and_stored: number;
  top_headlines: string[];
};

type NewsSummary = {
  articles_scored: number;
  avg_finbert_sentiment_score: number | null;
  avg_weighted_article_score: number | null;
  avg_confidence: number | null;
  label_counts: { bullish: number; bearish: number; neutral: number };
  finbert_model: string;
};

type DayPoint = {
  day: string;
  avg_sentiment: number;
  avg_final: number;
  count: number;
};

type Analytics = {
  summary: NewsSummary;
  series: DayPoint[];
};

function fmt(n: number | null | undefined, digits = 3) {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

function NewsScoreChart({ series }: { series: DayPoint[] }) {
  if (series.length === 0) {
    return (
      <div className="flex h-[220px] items-center justify-center rounded-lg border border-dashed border-border text-sm text-muted-foreground">
        No dated history yet. After you sync news, daily averages will appear here.
      </div>
    );
  }

  const data = series.map((d) => ({
    ...d,
    label: d.day.slice(5),
  }));

  return (
    <div className="h-[260px] w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis
            dataKey="label"
            tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "var(--border)" }}
          />
          <YAxis
            tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "var(--border)" }}
            width={44}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload as DayPoint;
              return (
                <div
                  className="rounded-lg border border-border px-3 py-2 text-xs shadow-md"
                  style={{ background: "var(--card)" }}
                >
                  <p className="font-medium text-foreground">{p.day}</p>
                  <p className="mt-1 text-muted-foreground">
                    <span className="text-foreground">Weighted avg</span> {p.avg_final.toFixed(3)}
                  </p>
                  <p className="text-muted-foreground">
                    <span className="text-foreground">FinBERT pos−neg</span> {p.avg_sentiment.toFixed(3)}
                  </p>
                  <p className="mt-1 text-muted-foreground">
                    Articles that day: <span className="text-foreground">{p.count}</span>
                  </p>
                </div>
              );
            }}
          />
          <Legend
            wrapperStyle={{ fontSize: "12px", paddingTop: 8 }}
            formatter={(value) =>
              value === "avg_final" ? "Daily weighted score" : "Daily FinBERT (pos − neg)"
            }
          />
          <Line
            type="monotone"
            dataKey="avg_final"
            name="avg_final"
            stroke="var(--foreground)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
          <Line
            type="monotone"
            dataKey="avg_sentiment"
            name="avg_sentiment"
            stroke="var(--muted-foreground)"
            strokeWidth={1.5}
            strokeDasharray="4 4"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function NewsPage() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [analyticsErr, setAnalyticsErr] = useState<string | null>(null);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [syncErr, setSyncErr] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const loadArticles = useCallback(() => {
    setErr(null);
    return apiGet<{ articles: Article[] }>("/api/news?limit=100")
      .then((r) => setArticles(r.articles))
      .catch((e: Error) => setErr(e.message));
  }, []);

  const loadAnalytics = useCallback(() => {
    setAnalyticsErr(null);
    return apiGet<Analytics>("/api/news/analytics?max_days=90")
      .then((r) => setAnalytics(r))
      .catch((e: Error) => {
        const msg = e.message;
        const looks404 =
          /not\s*found/i.test(msg) || msg.includes('"detail"') && msg.includes("Not Found");
        if (looks404) {
          setAnalyticsErr(
            "Analytics route not found (404). The process on port 8000 is probably an old btc-paper-api. " +
              "Stop it, then from the repo root run: btc-paper-api — or free port 8000 and run npm run dev from web/ so a fresh API starts.",
          );
          return;
        }
        setAnalyticsErr(msg);
      });
  }, []);

  useEffect(() => {
    void loadArticles();
    void loadAnalytics();
  }, [loadArticles, loadAnalytics]);

  const onRefresh = async () => {
    setSyncMsg(null);
    setSyncErr(null);
    setSyncing(true);
    try {
      const r = await apiPost<SyncResult>("/api/news/sync", {}, { timeoutMs: 300_000 });
      setSyncMsg(
        `Synced ${r.scored_and_stored} articles (${r.raw_article_count} raw from Yahoo). Reloading list…`,
      );
      await Promise.all([loadArticles(), loadAnalytics()]);
      setSyncMsg(
        `Done — stored ${r.scored_and_stored} articles (${r.raw_article_count} raw from Yahoo).`,
      );
    } catch (e) {
      setSyncErr((e as Error).message);
    } finally {
      setSyncing(false);
    }
  };

  if (err) {
    return <p className="text-destructive">{err}</p>;
  }

  const s = analytics?.summary;

  return (
    <div>
      <div className="mb-6 rounded-xl border border-border bg-card p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-white">
              News Sentimental Analysis
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
              Headlines from Yahoo (BTC-USD, IBIT, COIN, MSTR) scored with FinBERT and stored in your local SQLite
              — same path as the pipeline. Use <strong>Refresh Yahoo + FinBERT</strong> to pull new
              stories and re-score; first run may download model weights and take a few minutes.
            </p>
          </div>
          <AnimatedDownloadButton
            variant="primary"
            label="Refresh Yahoo + FinBERT"
            expandedWidth={300}
            pending={syncing}
            disabled={syncing}
            onClick={() => void onRefresh()}
          />
        </div>
        {syncMsg ? (
          <p className="mt-3 text-sm text-emerald-600 dark:text-emerald-400">{syncMsg}</p>
        ) : null}
        {syncErr ? <p className="mt-3 text-sm text-destructive">{syncErr}</p> : null}
      </div>

      <div className="mb-8 rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold text-white">FinBERT summary</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          <span className="font-mono">{s?.finbert_model ?? "—"}</span> · Raw score is FinBERT positive minus negative
          probability (~−1…+1). Weighted score multiplies by impact and recency (same as each article row).
        </p>
        {analyticsErr ? <p className="mt-2 text-sm text-destructive">{analyticsErr}</p> : null}
        {s && s.articles_scored > 0 ? (
          <>
            <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-lg border border-border/80 bg-background/40 px-3 py-2">
                <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">Articles scored</dt>
                <dd className="mt-0.5 font-mono text-lg text-foreground">{s.articles_scored}</dd>
              </div>
              <div className="rounded-lg border border-border/80 bg-background/40 px-3 py-2">
                <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">Avg FinBERT (pos − neg)</dt>
                <dd className="mt-0.5 font-mono text-lg text-foreground">
                  {fmt(s.avg_finbert_sentiment_score)}
                </dd>
              </div>
              <div className="rounded-lg border border-border/80 bg-background/40 px-3 py-2">
                <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">Avg weighted score</dt>
                <dd className="mt-0.5 font-mono text-lg text-foreground">
                  {fmt(s.avg_weighted_article_score)}
                </dd>
              </div>
              <div className="rounded-lg border border-border/80 bg-background/40 px-3 py-2">
                <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">Avg confidence</dt>
                <dd className="mt-0.5 font-mono text-lg text-foreground">{fmt(s.avg_confidence)}</dd>
              </div>
            </dl>
            <p className="mt-3 text-xs text-muted-foreground">
              Labels:{" "}
              <span className="text-emerald-500/90">bullish {s.label_counts.bullish}</span>
              {" · "}
              <span className="text-rose-500/90">bearish {s.label_counts.bearish}</span>
              {" · "}
              <span className="text-zinc-400">neutral {s.label_counts.neutral}</span>
            </p>
          </>
        ) : (
          <p className="mt-3 text-sm text-muted-foreground">
            No scored articles in the database yet. Run a sync or <code className="rounded bg-muted px-1">btc-paper-run</code>.
          </p>
        )}

        <h3 className="mb-2 mt-8 text-sm font-semibold text-white">News sentiment over time</h3>
        <p className="mb-4 text-xs text-muted-foreground">
          Per calendar day (UTC): mean weighted score (solid) and mean raw FinBERT pos−neg (dashed). Hover a point for
          counts and both averages.
        </p>
        <ClientOnly fallback={<div className="h-[260px] animate-pulse rounded-lg bg-muted/30" />}>
          <NewsScoreChart series={analytics?.series ?? []} />
        </ClientOnly>
      </div>

      {!articles.length ? (
        <p className="text-muted-foreground">No articles yet. Click Refresh above or run btc-paper-run.</p>
      ) : (
        <ul className="space-y-3">
          {articles.map((row) => (
            <li
              key={String(row.id ?? row.url)}
              className="rounded-lg border border-border bg-card p-4 text-sm"
            >
              <a
                href={String(row.url || "#")}
                target="_blank"
                rel="noreferrer"
                className="font-semibold text-white hover:text-white/90 hover:underline"
              >
                {String(row.headline ?? "")}
              </a>
              <div className="mt-2 text-xs text-muted-foreground">
                {String(row.source ?? "")} · {String(row.sentiment_label ?? "—")} (
                {Number(row.sentiment_score ?? 0).toFixed(2)}) · impact {String(row.impact ?? "—")}
              </div>
              {row.snippet ? (
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{String(row.snippet)}</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
