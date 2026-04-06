from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd

from btc_paper.config import Settings
from btc_paper.technical.coingecko import (
    fetch_market_chart_hourly,
    fetch_ohlc,
    fetch_spot_price_usd,
    ohlc_to_rows,
)
from btc_paper.technical.indicators import TimeframeAnalysis, analyze_timeframe, build_df_from_rows


def hourly_points_to_rows(
    points: List[Tuple[int, float]],
) -> List[Tuple[int, float, float, float, float, float]]:
    rows: List[Tuple[int, float, float, float, float, float]] = []
    for ts, px in points:
        rows.append((ts, px, px, px, px, 0.0))
    return rows


def safe_analyze_timeframe(df, label: str) -> Optional[TimeframeAnalysis]:
    if df is None or len(df) < 60:
        return None
    try:
        return analyze_timeframe(df, label)
    except Exception:  # noqa: BLE001
        return None


def _last_close_usd(df: Optional[pd.DataFrame]) -> Optional[float]:
    if df is None or len(df) == 0:
        return None
    try:
        return float(df["close"].iloc[-1])
    except (TypeError, ValueError, KeyError):
        return None


@dataclass
class LiveTechnicalReport:
    """Live BTC technical snapshot (CoinGecko + same logic as pipeline / btc-paper-test-tech)."""

    spot_usd: Optional[float]
    spot_error: Optional[str]
    spot_source: Optional[str]  # 1h_close | 4h_close | simple | None if error
    series_1h_candles: int
    series_1h_start: Optional[str]
    series_1h_end: Optional[str]
    series_4h_candles: int
    series_4h_start: Optional[str]
    series_4h_end: Optional[str]
    err_1h: Optional[str]
    err_4h: Optional[str]
    ta_1h: Optional[TimeframeAnalysis]
    ta_4h: Optional[TimeframeAnalysis]
    weight_1h: float
    weight_4h: float
    technical_score: Optional[float]
    blend_explanation: str


def compute_live_technical_with_dataframes(
    settings: Settings,
) -> Tuple[LiveTechnicalReport, Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    Same as compute_live_technical, plus OHLC DataFrames for chart APIs (when fetches succeed).
    """
    err_1h: Optional[str] = None
    err_4h: Optional[str] = None
    ta_1h: Optional[TimeframeAnalysis] = None
    ta_4h: Optional[TimeframeAnalysis] = None
    df_1h: Optional[pd.DataFrame] = None
    df_4h: Optional[pd.DataFrame] = None
    n1 = n4 = 0
    s1a = s1b = s4a = s4b = None

    # Fetch chart data first; derive spot from the last candle to avoid a separate /simple/price
    # call (reduces 429s on CoinGecko's public tier).
    try:
        hourly = fetch_market_chart_hourly(settings, days=30)
        df_1h = build_df_from_rows(hourly_points_to_rows(hourly))
        n1 = len(df_1h)
        if n1:
            s1a = str(df_1h.index[0])
            s1b = str(df_1h.index[-1])
        ta_1h = safe_analyze_timeframe(df_1h, "1h")
    except Exception as exc:  # noqa: BLE001
        err_1h = str(exc)
        df_1h = None

    try:
        raw_30 = fetch_ohlc(settings, days=30)
        df_4h = build_df_from_rows(ohlc_to_rows(raw_30))
        n4 = len(df_4h)
        if n4:
            s4a = str(df_4h.index[0])
            s4b = str(df_4h.index[-1])
        ta_4h = safe_analyze_timeframe(df_4h, "4h")
    except Exception as exc:  # noqa: BLE001
        err_4h = str(exc)
        df_4h = None

    spot: Optional[float] = None
    spot_err: Optional[str] = None
    spot_src: Optional[str] = None
    c1 = _last_close_usd(df_1h)
    c4 = _last_close_usd(df_4h)
    if c1 is not None:
        spot, spot_src = c1, "1h_close"
    elif c4 is not None:
        spot, spot_src = c4, "4h_close"
    else:
        try:
            spot = fetch_spot_price_usd(settings)
            spot_src = "simple"
        except Exception as exc:  # noqa: BLE001
            spot_err = str(exc)

    w1 = settings.technical_tf_1h_weight
    w4 = settings.technical_tf_4h_weight
    tech: Optional[float] = None
    explain = ""
    if ta_1h and ta_4h:
        tech = w1 * ta_1h.score + w4 * ta_4h.score
        explain = f"{w1} × ({ta_1h.score:+.4f}) + {w4} × ({ta_4h.score:+.4f})"
    elif ta_1h:
        tech = ta_1h.score
        explain = "4h unavailable — using 1h score only"
    elif ta_4h:
        tech = ta_4h.score
        explain = "1h unavailable — using 4h score only"
    else:
        explain = "Insufficient data — pipeline would use 0.0"

    report = LiveTechnicalReport(
        spot_usd=spot,
        spot_error=spot_err,
        spot_source=spot_src,
        series_1h_candles=n1,
        series_1h_start=s1a,
        series_1h_end=s1b,
        series_4h_candles=n4,
        series_4h_start=s4a,
        series_4h_end=s4b,
        err_1h=err_1h,
        err_4h=err_4h,
        ta_1h=ta_1h,
        ta_4h=ta_4h,
        weight_1h=w1,
        weight_4h=w4,
        technical_score=tech,
        blend_explanation=explain,
    )
    return report, df_1h, df_4h


def compute_live_technical(settings: Settings) -> LiveTechnicalReport:
    r, _, _ = compute_live_technical_with_dataframes(settings)
    return r
