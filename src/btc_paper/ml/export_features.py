"""
Export `data/ml_features.csv` from SQLite candles + stored signals.

Rows are **1h-aligned**: each row is one 1h bar; `target_up_*` in training uses row shifts
(`steps_ahead` = hours). Requires enough 1h history for indicators (≥60 bars) and 4h candles
overlapping the same period.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Tuple

import pandas as pd

from btc_paper import db
from btc_paper.config import Settings, load_settings
from btc_paper.ml.feature_schema import FEATURE_COLUMNS
from btc_paper.ml.features_live import build_live_ml_feature_row
from btc_paper.technical.indicators import analyze_timeframe, build_df_from_rows


def _candle_row_to_tuple(r: sqlite3.Row) -> tuple:
    return (
        int(r["ts"]),
        float(r["open"]),
        float(r["high"]),
        float(r["low"]),
        float(r["close"]),
        float(r["volume"] or 0.0),
    )


def _parse_run_at(val: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _signal_scores_at(signals: List[sqlite3.Row], bar_end: pd.Timestamp) -> Tuple[float, float]:
    """Last signal on or before `bar_end` (UTC). Falls back to (0, 0) if none."""
    bar_utc = bar_end
    if bar_utc.tzinfo is None:
        bar_utc = bar_utc.tz_localize("UTC")
    best: Optional[Tuple[datetime, float, float]] = None
    for row in signals:
        ra = _parse_run_at(row["run_at"])
        if ra is None:
            continue
        if ra <= bar_utc.to_pydatetime().astimezone(timezone.utc):
            if best is None or ra > best[0]:
                best = (ra, float(row["news_score"]), float(row["technical_score"]))
    if best is None:
        return 0.0, 0.0
    return best[1], best[2]


def _safe_analyze(df: pd.DataFrame, label: str):
    if df is None or len(df) < 60:
        return None
    try:
        return analyze_timeframe(df, label)
    except Exception:  # noqa: BLE001
        return None


def _technical_at_bar(
    settings: Settings,
    ta_1h,
    ta_4h,
) -> float:
    if ta_1h and ta_4h:
        return (
            settings.technical_tf_1h_weight * ta_1h.score
            + settings.technical_tf_4h_weight * ta_4h.score
        )
    if ta_1h:
        return float(ta_1h.score)
    if ta_4h:
        return float(ta_4h.score)
    return 0.0


def export_ml_features_csv(
    settings: Settings,
    *,
    output_path: Path,
    min_bars: int = 60,
    tail_rows: int = 4000,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with db.connect(settings) as conn:
        rows_1h = db.fetch_candles_all(conn, timeframe="1h")
        rows_4h = db.fetch_candles_all(conn, timeframe="4h")
        sig_rows = db.fetch_signals_chronological(conn)

    if len(rows_1h) < min_bars + 25:
        raise RuntimeError(
            f"Need at least {min_bars + 25} 1h candles in SQLite; found {len(rows_1h)}. "
            "Run `btc-paper-run` several times to populate history."
        )

    df_1h = build_df_from_rows([_candle_row_to_tuple(r) for r in rows_1h])
    df_4h = build_df_from_rows([_candle_row_to_tuple(r) for r in rows_4h]) if rows_4h else pd.DataFrame()

    n = len(df_1h)
    start_i = max(min_bars, n - tail_rows)
    end_i = n - 25  # leave room for 24h-ahead label in training

    out_rows: List[dict[str, Any]] = []
    for i in range(start_i, end_i):
        sub1 = df_1h.iloc[: i + 1]
        bar_end = sub1.index[-1]
        ta_1h = _safe_analyze(sub1, "1h")
        sub4 = df_4h[df_4h.index <= bar_end] if len(df_4h) else pd.DataFrame()
        ta_4h = _safe_analyze(sub4, "4h") if len(sub4) >= min_bars else None

        news_sig, tech_sig = _signal_scores_at(sig_rows, bar_end)
        tech_computed = _technical_at_bar(settings, ta_1h, ta_4h)
        # Prefer recomputed technicals at the bar; use stored signal technical if TA failed.
        technical_score = tech_computed if (ta_1h or ta_4h) else tech_sig
        news_score = news_sig

        px = float(sub1["close"].iloc[-1])
        feats = build_live_ml_feature_row(
            settings,
            news_score=news_score,
            technical_score=technical_score,
            ta_1h=ta_1h,
            ta_4h=ta_4h,
            df_1h=sub1,
            df_4h=sub4 if len(sub4) else None,
            btc_price=px,
        )
        feats["timestamp"] = bar_end.isoformat()
        out_rows.append(feats)

    cols = ["timestamp"] + FEATURE_COLUMNS
    pd.DataFrame(out_rows)[cols].to_csv(output_path, index=False)
    return len(out_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export ml_features.csv from the app SQLite DB.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/ml_features.csv"),
        help="Output CSV path",
    )
    parser.add_argument(
        "--tail-rows",
        type=int,
        default=4000,
        help="Max 1h bars to export from the end (runtime vs history tradeoff)",
    )
    args = parser.parse_args()
    settings = load_settings()
    n = export_ml_features_csv(settings, output_path=args.output, tail_rows=args.tail_rows)
    print(f"Wrote {n} rows to {args.output.resolve()}")


if __name__ == "__main__":
    main()
