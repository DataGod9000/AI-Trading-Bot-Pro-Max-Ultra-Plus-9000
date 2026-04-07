from __future__ import annotations

import numpy as np
import pandas as pd


def _safe_float(x: float) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    if not np.isfinite(v):
        return 0.0
    return v


def cumulative_return(equity: pd.Series, *, initial_capital: float) -> float:
    eq = equity.astype(float)
    if len(eq) == 0:
        return 0.0
    return _safe_float(eq.iloc[-1] / float(initial_capital) - 1.0)


def annualized_return(net_returns: pd.Series, *, bars_per_year: int) -> float:
    r = net_returns.astype(float).fillna(0.0)
    if len(r) == 0:
        return 0.0
    avg = float(r.mean())
    return _safe_float(avg * float(bars_per_year))


def annualized_volatility(net_returns: pd.Series, *, bars_per_year: int) -> float:
    r = net_returns.astype(float).fillna(0.0)
    if len(r) < 2:
        return 0.0
    vol = float(r.std(ddof=0))
    return _safe_float(vol * float(np.sqrt(bars_per_year)))


def sharpe_ratio(net_returns: pd.Series, *, bars_per_year: int) -> float:
    ar = annualized_return(net_returns, bars_per_year=bars_per_year)
    av = annualized_volatility(net_returns, bars_per_year=bars_per_year)
    if av <= 1e-12:
        return 0.0
    return _safe_float(ar / av)


def sortino_ratio(net_returns: pd.Series, *, bars_per_year: int) -> float:
    r = net_returns.astype(float).fillna(0.0)
    downside = r.where(r < 0.0, 0.0)
    dr = annualized_return(r, bars_per_year=bars_per_year)
    dv = float(downside.std(ddof=0)) * float(np.sqrt(bars_per_year))
    if dv <= 1e-12:
        return 0.0
    return _safe_float(dr / dv)


def max_drawdown(drawdown: pd.Series) -> float:
    dd = drawdown.astype(float).fillna(0.0)
    if len(dd) == 0:
        return 0.0
    return _safe_float(float(dd.min()))


def calmar_ratio(net_returns: pd.Series, drawdown: pd.Series, *, bars_per_year: int) -> float:
    ar = annualized_return(net_returns, bars_per_year=bars_per_year)
    mdd = abs(max_drawdown(drawdown))
    if mdd <= 1e-12:
        return 0.0
    return _safe_float(ar / mdd)


def win_rate(net_returns: pd.Series) -> float:
    r = net_returns.astype(float).fillna(0.0)
    if len(r) == 0:
        return 0.0
    return _safe_float(float((r > 0.0).mean()))


def trade_count_from_positions(position: pd.Series) -> int:
    """
    Approximate trades as number of non-zero position changes.
    Trade log generation comes later; this is a stable early metric.
    """
    pos = position.astype(float).fillna(0.0)
    n = int((pos.diff().abs() > 1e-12).sum())
    return max(0, n)


def avg_trade_return(net_returns: pd.Series, position: pd.Series) -> float:
    # Placeholder: per-trade segmentation added in Phase 2.
    tc = trade_count_from_positions(position)
    if tc <= 0:
        return 0.0
    r = net_returns.astype(float).fillna(0.0)
    return _safe_float(float(r.sum() / tc))

