from __future__ import annotations

import numpy as np
import pandas as pd

from btc_paper.backtest.schemas import SizingMode


def realized_volatility(returns: pd.Series, *, window: int) -> pd.Series:
    r = returns.astype(float).fillna(0.0)
    w = int(max(2, window))
    return r.rolling(w).std(ddof=0).fillna(0.0)


def size_exposure(
    *,
    direction: pd.Series,
    confidence: pd.Series,
    returns: pd.Series,
    mode: SizingMode,
    max_position_size: float,
    target_volatility: float,
    vol_window: int,
) -> pd.Series:
    """
    Produce a signed target exposure in [-max_position_size, +max_position_size].

    Modes:
    - fixed: size=1.0
    - confidence: size=abs(score) (clipped 0..1)
    - confidence_vol: size=abs(score) * (target_vol / realized_vol) with clipping
    """
    d = direction.astype(float).fillna(0.0)
    conf = confidence.astype(float).fillna(0.0).clip(lower=0.0, upper=1.0)
    max_pos = float(max(0.0, max_position_size))

    if mode == "fixed":
        raw_size = pd.Series(1.0, index=d.index)
    elif mode == "confidence":
        raw_size = conf
    elif mode == "confidence_vol":
        vol = realized_volatility(returns, window=vol_window)
        tv = float(max(1e-9, target_volatility))
        # If vol is near-zero (flat history), do not blow up size.
        scale = tv / vol.replace(0.0, np.nan)
        scale = scale.replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(0.0, 10.0)
        raw_size = conf * scale
    else:
        raw_size = pd.Series(1.0, index=d.index)

    exposure = (d * raw_size).clip(lower=-max_pos, upper=max_pos)
    return exposure.rename("target_position")

