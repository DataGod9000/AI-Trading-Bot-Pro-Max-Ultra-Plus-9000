from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import yfinance as yf

from btc_paper import db
from btc_paper.config import load_settings


def _to_epoch(ts: pd.Timestamp) -> int:
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return int(ts.timestamp())


def fetch_btc_usd_1h_history(*, period: str = "1y") -> pd.DataFrame:
    """
    Fetch BTC-USD 1h OHLCV via yfinance.

    Notes:
    - Yahoo can limit intraday lookback. If 1y is unavailable, retry smaller periods.
    - Returned index is timezone-aware or assumed UTC.
    """
    df = yf.download("BTC-USD", period=period, interval="1h", auto_adjust=False, progress=False, group_by="column")
    if df is None or df.empty:
        return pd.DataFrame()
    # Some yfinance versions return MultiIndex columns (e.g. ("Open","BTC-USD")); flatten.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [str(a).lower() for a, _ in df.columns.to_list()]
    else:
        df.columns = [str(c).lower() for c in df.columns]
    df = df.rename(columns=str.title)
    # Standardize columns: Open High Low Close Volume
    cols = {c.lower(): c for c in df.columns}
    df = df.rename(columns={cols.get("open", "Open"): "open"})
    df = df.rename(columns={cols.get("high", "High"): "high"})
    df = df.rename(columns={cols.get("low", "Low"): "low"})
    df = df.rename(columns={cols.get("close", "Close"): "close"})
    df = df.rename(columns={cols.get("volume", "Volume"): "volume"})
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    return df


def backfill_prices_to_sqlite(*, timeframe: str = "1h", period: str = "1y") -> int:
    settings = load_settings()
    df = fetch_btc_usd_1h_history(period=period)
    if df.empty:
        raise RuntimeError("No data returned from yfinance for BTC-USD 1h.")

    rows = []
    for idx, r in df.iterrows():
        rows.append(
            (
                _to_epoch(idx),
                float(r["open"]),
                float(r["high"]),
                float(r["low"]),
                float(r["close"]),
                float(r.get("volume", 0.0) or 0.0),
            )
        )

    with db.connect(settings) as conn:
        n = db.upsert_candles(conn, timeframe, rows)
    return n


def main(argv: Optional[list[str]] = None) -> None:
    p = argparse.ArgumentParser(description="Backfill BTC-USD 1h candles into SQLite (idempotent).")
    p.add_argument("--timeframe", default="1h", help="candles.timeframe value (default: 1h)")
    p.add_argument("--period", default="1y", help="yfinance period (default: 1y)")
    args = p.parse_args(argv)

    n = backfill_prices_to_sqlite(timeframe=str(args.timeframe), period=str(args.period))
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    print(f"[backfill_prices] {now} upserted_rows={n} timeframe={args.timeframe} period={args.period}")


if __name__ == "__main__":
    main()

