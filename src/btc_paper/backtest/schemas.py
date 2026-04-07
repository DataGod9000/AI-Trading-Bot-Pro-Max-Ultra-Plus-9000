from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


SizingMode = Literal["fixed", "confidence", "confidence_vol"]


@dataclass(frozen=True)
class BacktestParams:
    sizing_mode: SizingMode = "confidence"
    buy_threshold: float = 0.08
    sell_threshold: float = -0.08
    fee_bps: float = 0.0
    slippage_bps: float = 0.0
    vol_window: int = 72
    max_position_size: float = 1.0
    target_volatility: float = 0.20
    initial_capital: float = 10_000.0
    bars_per_year: int = 8760  # 1h bars
    benchmark: Literal["buy_hold"] = "buy_hold"
    start_iso: Optional[str] = None
    end_iso: Optional[str] = None


@dataclass(frozen=True)
class BacktestSummary:
    cumulative_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    win_rate: float
    trade_count: int
    avg_trade_return: float
    total_turnover: float
    total_cost_paid: float
    benchmark_cumulative_return: float
    alpha_vs_benchmark: float


@dataclass(frozen=True)
class BacktestResult:
    summary: BacktestSummary
    equity_curve: list[dict[str, float | str]]
    drawdown_curve: list[dict[str, float | str]]
    benchmark_curve: list[dict[str, float | str]]
    exposure_curve: list[dict[str, float | str]]
    trades: list[dict[str, float | int | str]]
    params: dict[str, float | int | str | None]

