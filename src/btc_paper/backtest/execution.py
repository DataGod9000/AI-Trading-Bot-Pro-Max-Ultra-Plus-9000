from __future__ import annotations

import pandas as pd


def execute_next_bar(target_position: pd.Series) -> pd.Series:
    """
    Default execution assumption:
      target at bar t is executed at bar t+1.

    The executed position is the exposure held over bar t's return.
    """
    return target_position.shift(1).fillna(0.0).rename("position")


def turnover(position: pd.Series) -> pd.Series:
    """Turnover is absolute change in executed position."""
    pos = position.astype(float).fillna(0.0)
    return pos.diff().abs().fillna(0.0).rename("turnover")


def apply_costs(
    *,
    gross_return: pd.Series,
    turnover: pd.Series,
    fee_bps: float,
    slippage_bps: float,
) -> tuple[pd.Series, pd.Series]:
    """
    Simple turnover-based cost model applied when position changes.
    cost_return = turnover * (fee_bps + slippage_bps) / 10_000
    """
    total_bps = float(fee_bps) + float(slippage_bps)
    cost = turnover.astype(float).fillna(0.0) * (total_bps / 10_000.0)
    net = gross_return.astype(float).fillna(0.0) - cost
    return net.rename("net_return"), cost.rename("cost")

