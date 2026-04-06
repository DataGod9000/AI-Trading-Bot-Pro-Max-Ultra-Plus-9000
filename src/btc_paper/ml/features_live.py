"""Build a single feature row for ML inference from live pipeline state."""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from btc_paper.config import Settings
from btc_paper.ml.feature_schema import FEATURE_COLUMNS
from btc_paper.technical.indicators import TimeframeAnalysis


def _bollinger_position(close: float, upper: Optional[float], lower: Optional[float]) -> float:
    if upper is None or lower is None or upper <= lower:
        return 0.5
    return float(np.clip((close - lower) / (upper - lower), 0.0, 1.0))


def _bar_return(close: pd.Series, bars: int = 1) -> float:
    if len(close) < bars + 1:
        return 0.0
    a, b = float(close.iloc[-(bars + 1)]), float(close.iloc[-1])
    if a == 0.0:
        return 0.0
    return (b - a) / a


def _volume_change(vol: pd.Series) -> float:
    if len(vol) < 2:
        return 0.0
    a, b = float(vol.iloc[-2]), float(vol.iloc[-1])
    if abs(a) < 1e-12:
        return 0.0
    return (b - a) / a


def _from_ta(ta: Optional[TimeframeAnalysis]) -> dict[str, float]:
    if ta is None:
        return {
            "ema_trend": 0.0,
            "rsi": 50.0,
            "bb_pos": 0.5,
            "bb_width": 0.0,
            "macd_score": 0.0,
            "close": 0.0,
        }
    d = ta.detail
    cl = float(d.get("close") or 0.0)
    up, lo = d.get("bb_upper"), d.get("bb_lower")
    up_f = float(up) if up is not None else None
    lo_f = float(lo) if lo is not None else None
    bw = d.get("bb_width")
    bw_f = float(bw) if bw is not None else 0.0
    return {
        "ema_trend": float(ta.trend),
        "rsi": float(ta.rsi) if np.isfinite(ta.rsi) else 50.0,
        "bb_pos": _bollinger_position(cl, up_f, lo_f),
        "bb_width": bw_f,
        "macd_score": float(ta.macd_signal),
        "close": cl,
    }


def build_live_ml_feature_row(
    settings: Settings,
    *,
    news_score: float,
    technical_score: float,
    ta_1h: Optional[TimeframeAnalysis],
    ta_4h: Optional[TimeframeAnalysis],
    df_1h: Optional[pd.DataFrame],
    df_4h: Optional[pd.DataFrame],
    btc_price: float,
) -> Dict[str, float]:
    """
    Map app state → PRD feature vector. Uses CoinGecko-derived OHLC (PRD mentions Binance;
    indicators are the same EMA/RSI/BB/MACD logic).
    """
    h1 = _from_ta(ta_1h)
    h4 = _from_ta(ta_4h)

    if df_1h is not None and len(df_1h) > 0:
        c1 = df_1h["close"].astype(float)
        v1 = df_1h["volume"].astype(float) if "volume" in df_1h.columns else pd.Series([0.0] * len(df_1h))
        ret_1h = _bar_return(c1, 1)
        vc_1h = _volume_change(v1)
        price_close = float(c1.iloc[-1])
    else:
        ret_1h, vc_1h = 0.0, 0.0
        price_close = float(btc_price) if btc_price else h1["close"]

    if df_4h is not None and len(df_4h) > 0:
        c4 = df_4h["close"].astype(float)
        v4 = df_4h["volume"].astype(float) if "volume" in df_4h.columns else pd.Series([0.0] * len(df_4h))
        ret_4h = _bar_return(c4, 1)
        vc_4h = _volume_change(v4)
    else:
        ret_4h, vc_4h = 0.0, 0.0

    # Rule-only blend for the ML feature column (stable vs classic 60/40; see `ml_rule_*` settings).
    final_rule_score = float(settings.ml_rule_news_weight) * float(news_score) + float(
        settings.ml_rule_technical_weight
    ) * float(technical_score)

    row: Dict[str, Any] = {
        "news_score": float(news_score),
        "technical_score": float(technical_score),
        "final_rule_score": float(final_rule_score),
        "ema_trend_1h": h1["ema_trend"],
        "ema_trend_4h": h4["ema_trend"],
        "rsi_1h": h1["rsi"],
        "rsi_4h": h4["rsi"],
        "bollinger_position_1h": h1["bb_pos"],
        "bollinger_position_4h": h4["bb_pos"],
        "bollinger_width_1h": h1["bb_width"],
        "bollinger_width_4h": h4["bb_width"],
        "macd_score_1h": h1["macd_score"],
        "macd_score_4h": h4["macd_score"],
        "return_1h": float(ret_1h),
        "return_4h": float(ret_4h),
        "volume_change_1h": float(vc_1h),
        "volume_change_4h": float(vc_4h),
        "price_close": float(price_close),
    }
    for k in FEATURE_COLUMNS:
        v = row[k]
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            row[k] = 0.0
    return {k: float(row[k]) for k in FEATURE_COLUMNS}
