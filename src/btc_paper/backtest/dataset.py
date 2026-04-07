from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from btc_paper import db
from btc_paper.config import Settings
from btc_paper.signal_engine import combine_scores
from btc_paper.backtest.reconstruct import (
    reconstruct_news_score_series,
    reconstruct_technical_score_series,
)


def _parse_run_at(val: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class BacktestDataset:
    df: pd.DataFrame
    source: str


def generate_backtest_dataset(
    settings: Settings,
    *,
    timeframe: str = "1h",
    start_iso: str | None = None,
    end_iso: str | None = None,
    reconstruct_signal: bool = False,
    news_lookback_hours: Optional[int] = None,
) -> BacktestDataset:
    """
    Build a backtest-ready, time-ordered dataframe.

    Default source is SQLite:
    - OHLCV from candles(timeframe='1h')
    - final_score from the latest signal at or before each bar time

    Notes:
    - Avoid lookahead: we only use signals with run_at <= bar timestamp.
    - If a bar has no prior signal, its final_score is 0.0.
    """
    with db.connect(settings) as conn:
        c_rows = db.fetch_candles_all(conn, timeframe=timeframe)
        sig_bar_rows = db.fetch_signal_bars_all(conn, timeframe=timeframe)
        sig_rows = conn.execute(
            """
            SELECT run_at, final_score
            FROM signals
            ORDER BY datetime(run_at) ASC
            """
        ).fetchall()
        news_rows = conn.execute(
            """
            SELECT published_at, scraped_at, final_article_score
            FROM news_articles
            WHERE final_article_score IS NOT NULL
            ORDER BY datetime(COALESCE(published_at, scraped_at)) ASC, datetime(scraped_at) ASC
            """
        ).fetchall()

    if not c_rows:
        return BacktestDataset(df=pd.DataFrame(), source="sqlite")

    df = pd.DataFrame(c_rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["ts"], unit="s", utc=True)
    df = df.drop(columns=["ts"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Optional date range filter (ISO strings, UTC assumed if no tz)
    if start_iso:
        start = pd.to_datetime(start_iso, utc=True)
        df = df[df["timestamp"] >= start]
    if end_iso:
        end = pd.to_datetime(end_iso, utc=True)
        df = df[df["timestamp"] <= end]
    df = df.reset_index(drop=True)

    # Prefer cached per-bar signals if present (fast + dense history).
    if sig_bar_rows:
        sb = pd.DataFrame(
            sig_bar_rows,
            columns=[
                "ts",
                "news_score",
                "technical_score",
                "ml_score",
                "final_score",
                "source",
                "computed_at",
            ],
        )
        sb["timestamp"] = pd.to_datetime(sb["ts"], unit="s", utc=True)
        sb = sb.drop(columns=["ts"]).sort_values("timestamp")
        out = df.merge(sb[["timestamp", "final_score"]], on="timestamp", how="left", suffixes=("", "_sb"))
        if "final_score_sb" in out.columns:
            out["final_score"] = out["final_score_sb"].fillna(out["final_score"]).astype(float).fillna(0.0)
            out = out.drop(columns=["final_score_sb"])
        else:
            # df didn't have final_score yet; merged column is the reconstructed score.
            out["final_score"] = out["final_score"].astype(float).fillna(0.0)
        out["asset_return"] = out["close"].astype(float).pct_change().fillna(0.0)
        return BacktestDataset(df=out, source="sqlite_signal_bars")

    # Map signals -> bars in a single pass (O(n))
    sig = []
    for r in sig_rows:
        ra = _parse_run_at(r["run_at"])
        if ra is None:
            continue
        sig.append((ra, float(r["final_score"])))
    sig.sort(key=lambda x: x[0])

    scores = []
    j = 0
    last = 0.0
    times = df["timestamp"].dt.to_pydatetime()
    for t in list(times):
        # pandas gives tz-aware UTC datetimes; normalize defensively
        tt = t.astimezone(timezone.utc)
        while j < len(sig) and sig[j][0] <= tt:
            last = sig[j][1]
            j += 1
        scores.append(float(last))

    df["final_score"] = pd.Series(scores, dtype="float64")
    df["asset_return"] = df["close"].astype(float).pct_change().fillna(0.0)
    if not reconstruct_signal:
        return BacktestDataset(df=df, source="sqlite")

    # Retroactive reconstruction (no lookahead) using only information available up to each bar.
    lookback = int(news_lookback_hours or settings.news_lookback_hours or 24)
    news_df = pd.DataFrame(news_rows, columns=["published_at", "scraped_at", "final_article_score"])
    news_score = reconstruct_news_score_series(bars_ts=df["timestamp"], articles=news_df, lookback_hours=lookback)

    # Technicals from OHLCV prefix analysis (1h only for now; can add 4h blend later).
    ohlc_idx = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
    tech_score, _rsi = reconstruct_technical_score_series(ohlcv=ohlc_idx)
    tech_score = tech_score.reindex(ohlc_idx.index).fillna(0.0)

    # Combine using the same production blend logic (ML inactive in reconstruction default).
    finals = []
    for ns, ts in zip(news_score.tolist(), tech_score.tolist()):
        sig = combine_scores(
            settings,
            news_score=float(ns),
            technical_score=float(ts),
            news_summary="retro",
            technical_summary="retro",
            ml_score=0.0,
            ml_active=False,
            ml_payload=None,
        )
        finals.append(float(sig.final_score))

    out = df.copy()
    out["news_score"] = news_score.values
    out["technical_score"] = tech_score.values
    out["final_score"] = pd.Series(finals, dtype="float64")
    return BacktestDataset(df=out, source="sqlite_reconstructed")

