from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from btc_paper import db
from btc_paper.backtest.dataset import generate_backtest_dataset
from btc_paper.backtest.reconstruct import reconstruct_news_score_series, reconstruct_technical_score_series
from btc_paper.config import load_settings
from btc_paper.signal_engine import combine_scores


def reconstruct_and_store(*, timeframe: str = "1h", lookback_hours: int = 24) -> int:
    settings = load_settings()
    ds = generate_backtest_dataset(settings, timeframe=timeframe)
    df = ds.df
    if df is None or len(df) == 0:
        return 0

    # News: from stored articles up to each bar
    with db.connect(settings) as conn:
        news_rows = conn.execute(
            """
            SELECT published_at, scraped_at, final_article_score
            FROM news_articles
            WHERE final_article_score IS NOT NULL
            ORDER BY datetime(COALESCE(published_at, scraped_at)) ASC, datetime(scraped_at) ASC
            """
        ).fetchall()

    news_df = pd.DataFrame(news_rows, columns=["published_at", "scraped_at", "final_article_score"])
    news_score = reconstruct_news_score_series(
        bars_ts=df["timestamp"],
        articles=news_df,
        lookback_hours=lookback_hours,
    )

    # Technicals: lookahead-safe (causal rolling/ewm)
    ohlc = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
    tech_score, _ = reconstruct_technical_score_series(ohlcv=ohlc)

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

    computed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows = []
    for t, ns, ts, fs in zip(df["timestamp"].tolist(), news_score.tolist(), tech_score.tolist(), finals):
        ts_epoch = int(pd.Timestamp(t).timestamp())
        rows.append((ts_epoch, float(ns), float(ts), 0.0, float(fs), "reconstructed_v1", computed_at))

    with db.connect(settings) as conn:
        return db.upsert_signal_bars(conn, timeframe=timeframe, rows=rows)


def main(argv: Optional[list[str]] = None) -> None:
    p = argparse.ArgumentParser(description="Reconstruct historical signals (no lookahead) and cache into SQLite.")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--lookback-hours", type=int, default=24)
    args = p.parse_args(argv)

    n = reconstruct_and_store(timeframe=str(args.timeframe), lookback_hours=int(args.lookback_hours))
    print(f"[reconstruct_signals] upserted_rows={n} timeframe={args.timeframe} lookback_hours={args.lookback_hours}")


if __name__ == "__main__":
    main()

