from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def bollinger(
    series: pd.Series, period: int = 20, num_std: float = 2.0
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    mid = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def macd_hist(series: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
    ema12 = ema(series, 12)
    ema26 = ema(series, 26)
    line = ema12 - ema26
    signal = ema(line, 9)
    hist = line - signal
    return line, signal, hist


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    o = df["open"].resample(rule).first()
    h = df["high"].resample(rule).max()
    l = df["low"].resample(rule).min()
    c = df["close"].resample(rule).last()
    v = df["volume"].resample(rule).sum() if "volume" in df.columns else None
    out = pd.DataFrame({"open": o, "high": h, "low": l, "close": c})
    if v is not None:
        out["volume"] = v
    return out.dropna()


@dataclass
class TimeframeAnalysis:
    timeframe: str
    score: float
    trend: int
    rsi: float
    rsi_signal: float
    bollinger_signal: float
    macd_signal: float
    volatility_high: bool
    detail: Dict[str, Any]


def analysis_to_breakdown_payload(ta: TimeframeAnalysis) -> Dict[str, Any]:
    """
    Merge indicator levels with contribution terms (rsi_s, bb_s, macd_s) for UI / stored signals.
    Matches analyze_timeframe: mean_rev = rsi_s + bb_s, halved if vol high; raw = trend + mean_rev + macd_s.
    """
    mean_rev = float(ta.rsi_signal + ta.bollinger_signal)
    mean_rev_eff = mean_rev * 0.5 if ta.volatility_high else mean_rev
    raw = float(ta.trend + mean_rev_eff + ta.macd_signal)
    return {
        **ta.detail,
        "trend_term": ta.trend,
        "rsi_s": float(ta.rsi_signal),
        "bb_s": float(ta.bollinger_signal),
        "macd_s": float(ta.macd_signal),
        "mean_rev_before_vol_dampen": mean_rev,
        "mean_rev_after_vol_dampen": mean_rev_eff,
        "volatility_high": ta.volatility_high,
        "raw_sum": raw,
        "normalized_score": float(ta.score),
    }


def _trend_score(close: float, ema20: float, ema50: float) -> int:
    if close > ema20 > ema50:
        return 1
    if close < ema20 < ema50:
        return -1
    return 0


def _last_valid(series: pd.Series) -> Optional[float]:
    s = series.dropna()
    if s.empty:
        return None
    return float(s.iloc[-1])


def analyze_timeframe(df: pd.DataFrame, label: str) -> TimeframeAnalysis:
    close = df["close"]
    e20 = ema(close, 20)
    e50 = ema(close, 50)
    r = rsi(close, 14)
    upper, mid, lower = bollinger(close, 20, 2.0)
    m_line, m_sig, _ = macd_hist(close)

    last_close = float(close.iloc[-1])
    le20 = _last_valid(e20)
    le50 = _last_valid(e50)
    lr = _last_valid(r)
    lu = _last_valid(upper)
    ll = _last_valid(lower)
    lm = _last_valid(mid)
    lml = _last_valid(m_line)
    lms = _last_valid(m_sig)

    trend = 0
    if le20 is not None and le50 is not None:
        trend = _trend_score(last_close, le20, le50)

    rsi_s = 0.0
    if lr is not None:
        if lr > 70:
            rsi_s = -0.5
        elif lr < 30:
            rsi_s = 0.5

    bb_s = 0.0
    if lu is not None and ll is not None:
        if last_close >= lu:
            bb_s = -0.5
        elif last_close <= ll:
            bb_s = 0.5

    macd_s = 0.0
    if lml is not None and lms is not None:
        if lml > lms:
            macd_s = 0.5
        elif lml < lms:
            macd_s = -0.5

    width = None
    vol_high = False
    if lu is not None and ll is not None and lm is not None and lm != 0:
        width = (lu - ll) / lm
        hist_width = ((upper - lower) / mid).dropna()
        if len(hist_width) >= 5:
            vol_high = bool(width > float(hist_width.median()) * 1.5)

    mean_rev = rsi_s + bb_s
    if vol_high:
        mean_rev *= 0.5

    raw = float(trend + mean_rev + macd_s)
    normalized = max(-1.0, min(1.0, raw / 2.5))

    detail = {
        "close": last_close,
        "ema20": le20,
        "ema50": le50,
        "rsi14": lr,
        "bb_upper": lu,
        "bb_lower": ll,
        "bb_mid": lm,
        "macd": lml,
        "macd_signal": lms,
        "bb_width": width,
    }
    return TimeframeAnalysis(
        timeframe=label,
        score=normalized,
        trend=trend,
        rsi=lr if lr is not None else float("nan"),
        rsi_signal=rsi_s,
        bollinger_signal=bb_s,
        macd_signal=macd_s,
        volatility_high=vol_high,
        detail=detail,
    )


def build_df_from_rows(rows: List[Tuple[int, float, float, float, float, float]]) -> pd.DataFrame:
    df = pd.DataFrame(
        rows,
        columns=["ts", "open", "high", "low", "close", "volume"],
    )
    df["dt"] = pd.to_datetime(df["ts"], unit="s", utc=True)
    df = df.set_index("dt").sort_index()
    return df
