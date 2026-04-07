"use client";

import { useEffect, useState } from "react";
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

type HistRow = {
  run_at: string;
  action: string;
  final_score: number;
  ml_score: number;
  ml_prob: number | null;
  p_1h: number | null;
  p_12h: number | null;
  p_24h: number | null;
  ml_bias: string | null;
};

type MlSummary = {
  metadata: Record<string, unknown> | null;
  meta_path: string;
  latest_signal: Record<string, unknown> | null;
  ml_block: Record<string, unknown> | null;
  weights: Record<string, unknown> | null;
  conflict_dampened: boolean;
  reason: string | null;
  history: HistRow[];
  settings: Record<string, number | boolean | string>;
};

function safeFloat(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

export default function MlPage() {
  const [histN, setHistN] = useState(45);
  const [data, setData] = useState<MlSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    apiGet<MlSummary>(`/api/ml/summary?hist_n=${histN}`)
      .then(setData)
      .catch((e: Error) => setErr(e.message));
  }, [histN]);

  if (err) {
    return <p className="text-destructive">{err}</p>;
  }
  if (!data) {
    return <p className="text-muted-foreground">Loading ML summary…</p>;
  }

  const latest = data.latest_signal;
  const ml = data.ml_block;
  const hp = (ml?.horizon_predictions as Record<string, Record<string, unknown>> | undefined) ?? {};
  const mlActive = Boolean(data.weights && data.weights.ml_active);

  const chartData = data.history
    .filter((h) => h.ml_score != null && !Number.isNaN(h.ml_score))
    .map((h) => ({
      run_at: h.run_at,
      ml_score: h.ml_score,
    }));

  return (
    <div>
      <div className="mb-6 rounded-xl border border-border bg-card p-6">
        <h1 className="text-2xl font-semibold tracking-tight">Machine learning signals</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          A breakdown of the ML layer for the latest runs: per-horizon up probabilities, the blended ml_score, and how
          it influenced the final decision. Values are read from{" "}
          <code className="rounded bg-muted px-1">signals.breakdown_json</code>.
        </p>
        <div className="mt-4 flex flex-wrap gap-4 text-sm">
          <label className="flex items-center gap-2">
            <span className="text-muted-foreground">History rows</span>
            <input
              type="number"
              min={5}
              max={200}
              step={5}
              value={histN}
              onChange={(e) => setHistN(Number(e.target.value))}
              className="w-20 rounded border border-border bg-background px-2 py-1 font-mono text-xs"
            />
          </label>
        </div>
        <div className="mt-4 text-xs text-muted-foreground">
          <div>
            Models dir: <code className="text-foreground">{data.meta_path}</code>
          </div>
          {data.metadata ? (
            <div className="mt-1">
              Feature version <strong>{String(data.metadata.feature_version ?? "?")}</strong> · trained{" "}
              <code>{String(data.metadata.trained_at ?? "?")}</code>
            </div>
          ) : (
            <p className="mt-1">No model_metadata.json — train and export artifacts first.</p>
          )}
          <div className="mt-2">
            ML_ENABLED={String(data.settings.ml_enabled)} · horizon weights{" "}
            {safeFloat(data.settings.ml_horizon_weight_1h)}/{safeFloat(data.settings.ml_horizon_weight_12h)}/
            {safeFloat(data.settings.ml_horizon_weight_24h)}
          </div>
        </div>
      </div>

      {!latest ? (
        <p className="text-muted-foreground">No signals in the database yet.</p>
      ) : (
        <>
          <div className="rounded-xl border border-border bg-card p-6">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">Latest pipeline run</h2>
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <div>
                <div className="text-xs text-muted-foreground">Final action</div>
                <div className="text-xl font-semibold">{String(latest.action)}</div>
                <div className="mt-1 font-mono text-xs text-muted-foreground">UTC {String(latest.run_at)}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Unified final score</div>
                <div className="font-mono text-xl font-semibold">
                  {safeFloat(latest.final_score) >= 0 ? "+" : ""}
                  {safeFloat(latest.final_score).toFixed(3)}
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  ML score (stored){" "}
                  {(() => {
                    const br = latest.breakdown as Record<string, unknown> | undefined;
                    const ms = br ? safeFloat(br.ml_score) : 0;
                    return `${ms >= 0 ? "+" : ""}${ms.toFixed(3)}`;
                  })()}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">ML layer</div>
                <div className="text-xl font-semibold">{mlActive ? "Active" : "Inactive"}</div>
                {data.conflict_dampened ? (
                  <p className="mt-2 text-xs text-amber-600">Conflict dampening was applied (×0.7).</p>
                ) : null}
              </div>
            </div>
          </div>

          {!ml || Object.keys(ml).length === 0 ? (
            <p className="mt-6 text-sm text-muted-foreground">
              This signal has no ML block — models were not loaded or ML was off.
            </p>
          ) : (
            <div className="mt-6">
              <h3 className="text-sm font-semibold">Horizon probabilities (latest)</h3>
              <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-5">
                <Mini label="P(up) 1h" v={safeFloat((hp.target_up_1h || {}).prob_up ?? 0.5)} />
                <Mini label="P(up) 12h" v={safeFloat((hp.target_up_12h || {}).prob_up ?? 0.5)} />
                <Mini label="P(up) 24h" v={safeFloat((hp.target_up_24h || {}).prob_up ?? 0.5)} />
                <Mini label="Blended ML prob" v={safeFloat(ml.ml_prob ?? 0.5)} />
                <div className="rounded-lg border border-border bg-card p-3">
                  <div className="text-[10px] uppercase text-muted-foreground">ML bias</div>
                  <div className="mt-1 font-mono text-sm font-semibold capitalize">
                    {String(ml.ml_bias ?? "neutral")}
                  </div>
                </div>
              </div>
            </div>
          )}

          {chartData.length > 1 ? (
            <div className="mt-8 h-64">
              <h3 className="mb-2 text-sm font-semibold">ML score over recent runs</h3>
              <ClientOnly>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <XAxis dataKey="run_at" tick={{ fontSize: 8 }} interval="preserveStartEnd" />
                    <YAxis domain={[-1.05, 1.05]} tick={{ fontSize: 10 }} />
                    <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)" }} />
                    <Line type="monotone" dataKey="ml_score" stroke="var(--primary)" dot strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </ClientOnly>
            </div>
          ) : null}

          <div className="mt-8 overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted">
                <tr>
                  <th className="p-2">run_at</th>
                  <th className="p-2">action</th>
                  <th className="p-2">final</th>
                  <th className="p-2">ml_score</th>
                  <th className="p-2">ml_prob</th>
                  <th className="p-2">p_1h</th>
                  <th className="p-2">p_12h</th>
                  <th className="p-2">p_24h</th>
                  <th className="p-2">bias</th>
                </tr>
              </thead>
              <tbody>
                {[...data.history].reverse().map((h) => (
                  <tr key={h.run_at} className="border-t border-border">
                    <td className="p-2 font-mono">{h.run_at}</td>
                    <td className="p-2">{h.action}</td>
                    <td className="p-2 font-mono">{h.final_score.toFixed(3)}</td>
                    <td className="p-2 font-mono">{h.ml_score.toFixed(3)}</td>
                    <td className="p-2 font-mono">{h.ml_prob != null ? h.ml_prob.toFixed(3) : "—"}</td>
                    <td className="p-2 font-mono">{h.p_1h != null ? h.p_1h.toFixed(3) : "—"}</td>
                    <td className="p-2 font-mono">{h.p_12h != null ? h.p_12h.toFixed(3) : "—"}</td>
                    <td className="p-2 font-mono">{h.p_24h != null ? h.p_24h.toFixed(3) : "—"}</td>
                    <td className="p-2">{h.ml_bias ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.reason ? (
            <details className="mt-6 rounded-lg border border-border bg-card p-4">
              <summary className="cursor-pointer text-sm font-medium">Full rationale (latest)</summary>
              <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">
                {data.reason}
              </pre>
            </details>
          ) : null}
        </>
      )}
    </div>
  );
}

function Mini({ label, v }: { label: string; v: number }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className="text-[10px] uppercase text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono text-sm font-semibold">{v.toFixed(3)}</div>
    </div>
  );
}
