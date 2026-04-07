from __future__ import annotations

import pandas as pd


def equity_curve(net_returns: pd.Series, *, initial_capital: float) -> pd.Series:
    r = net_returns.astype(float).fillna(0.0)
    eq = float(initial_capital) * (1.0 + r).cumprod()
    return eq.rename("equity")


def rolling_peak(equity: pd.Series) -> pd.Series:
    return equity.astype(float).cummax().rename("peak")


def drawdown(equity: pd.Series) -> pd.Series:
    eq = equity.astype(float)
    pk = rolling_peak(eq)
    dd = (eq / pk) - 1.0
    return dd.fillna(0.0).rename("drawdown")

