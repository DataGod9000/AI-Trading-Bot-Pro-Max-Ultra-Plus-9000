from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pandas as pd

from btc_paper.backtest.execution import apply_costs, execute_next_bar, turnover
from btc_paper.backtest.metrics import (
    annualized_return,
    annualized_volatility,
    avg_trade_return,
    calmar_ratio,
    cumulative_return,
    max_drawdown,
    sharpe_ratio,
    sortino_ratio,
    trade_count_from_positions,
    win_rate,
)
from btc_paper.backtest.portfolio import drawdown, equity_curve
from btc_paper.backtest.position_sizing import size_exposure
from btc_paper.backtest.schemas import BacktestParams, BacktestResult, BacktestSummary
from btc_paper.backtest.strategy import score_to_direction


def _to_series_payload(ts: pd.Series, y: pd.Series, key: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t, v in zip(ts.tolist(), y.astype(float).tolist()):
        out.append({"ts": str(t), key: float(v)})
    return out


def _trades_from_positions(
    *,
    ts: pd.Series,
    open_px: pd.Series,
    position: pd.Series,
    gross_return: pd.Series,
    net_return: pd.Series,
    equity: pd.Series,
) -> list[dict[str, float | int | str]]:
    """
    Create a simple trade log from executed positions.

    Trade definition (Phase 2):
    - Entry when position moves from 0 -> nonzero OR flips sign.
    - Exit when position moves to 0 OR flips sign.
    - Entry/exit price uses bar open when the executed position is first held.
    - PnL computed from compounding return series during the holding period.
    """
    tsv = ts.astype(str).tolist()
    op = open_px.astype(float).ffill().fillna(0.0).tolist()
    pos = position.astype(float).fillna(0.0).tolist()
    gross = gross_return.astype(float).fillna(0.0).tolist()
    net = net_return.astype(float).fillna(0.0).tolist()
    eq = equity.astype(float).ffill().fillna(0.0).tolist()

    trades: list[dict[str, float | int | str]] = []
    i = 0
    while i < len(pos):
        if abs(pos[i]) <= 1e-12:
            i += 1
            continue
        side = "LONG" if pos[i] > 0 else "SHORT"
        size = abs(float(pos[i]))
        entry_i = i
        entry_ts = tsv[i]
        entry_px = float(op[i])
        entry_eq = float(eq[i]) if i < len(eq) else 0.0

        j = i + 1
        while j < len(pos) and abs(pos[j]) > 1e-12 and (pos[j] > 0) == (pos[i] > 0):
            j += 1
        exit_i = min(j, len(pos) - 1)
        exit_ts = tsv[exit_i]
        exit_px = float(op[exit_i])

        gross_mult = 1.0
        net_mult = 1.0
        for k in range(entry_i, exit_i + 1):
            gross_mult *= 1.0 + float(gross[k])
            net_mult *= 1.0 + float(net[k])
        gross_r = float(gross_mult - 1.0)
        net_r = float(net_mult - 1.0)
        pnl_gross = float(entry_eq * gross_r)
        pnl_net = float(entry_eq * net_r)

        trades.append(
            {
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "side": side,
                "size": size,
                "entry_price": entry_px,
                "exit_price": exit_px,
                "holding_bars": int(exit_i - entry_i + 1),
                "gross_return": gross_r,
                "net_return": net_r,
                "gross_pnl": pnl_gross,
                "net_pnl": pnl_net,
            }
        )
        i = exit_i + 1
    return trades


def run_backtest(df: pd.DataFrame, params: BacktestParams) -> BacktestResult:
    """
    Core backtest orchestration.

    Expected columns:
    - timestamp (UTC)
    - close
    - asset_return (close-to-close pct)
    - final_score
    """
    if df is None or len(df) == 0:
        empty = BacktestSummary(
            cumulative_return=0.0,
            annualized_return=0.0,
            annualized_volatility=0.0,
            sharpe=0.0,
            sortino=0.0,
            max_drawdown=0.0,
            calmar=0.0,
            win_rate=0.0,
            trade_count=0,
            avg_trade_return=0.0,
            total_turnover=0.0,
            total_cost_paid=0.0,
            benchmark_cumulative_return=0.0,
            alpha_vs_benchmark=0.0,
        )
        return BacktestResult(
            summary=empty,
            equity_curve=[],
            drawdown_curve=[],
            benchmark_curve=[],
            exposure_curve=[],
            trades=[],
            params=asdict(params),
        )

    dfx = df.copy()
    dfx["timestamp"] = pd.to_datetime(dfx["timestamp"], utc=True)
    dfx = dfx.sort_values("timestamp").reset_index(drop=True)

    score = dfx["final_score"].astype(float).fillna(0.0)
    direction = score_to_direction(score, buy_threshold=params.buy_threshold, sell_threshold=params.sell_threshold)
    conf = score.abs().clip(0.0, 1.0).rename("confidence")

    target = size_exposure(
        direction=direction,
        confidence=conf,
        returns=dfx["asset_return"],
        mode=params.sizing_mode,
        max_position_size=params.max_position_size,
        target_volatility=params.target_volatility,
        vol_window=params.vol_window,
    )
    pos = execute_next_bar(target)
    to = turnover(pos)

    gross = (pos * dfx["asset_return"].astype(float).fillna(0.0)).rename("gross_return")
    net, cost = apply_costs(
        gross_return=gross,
        turnover=to,
        fee_bps=params.fee_bps,
        slippage_bps=params.slippage_bps,
    )

    eq = equity_curve(net, initial_capital=params.initial_capital)
    dd = drawdown(eq)

    # Benchmark: buy & hold (same initial capital)
    bench_eq = equity_curve(dfx["asset_return"].astype(float).fillna(0.0), initial_capital=params.initial_capital)

    strat_cum = cumulative_return(eq, initial_capital=params.initial_capital)
    bench_cum = cumulative_return(bench_eq, initial_capital=params.initial_capital)
    alpha = float(strat_cum - bench_cum)

    summary = BacktestSummary(
        cumulative_return=strat_cum,
        annualized_return=annualized_return(net, bars_per_year=params.bars_per_year),
        annualized_volatility=annualized_volatility(net, bars_per_year=params.bars_per_year),
        sharpe=sharpe_ratio(net, bars_per_year=params.bars_per_year),
        sortino=sortino_ratio(net, bars_per_year=params.bars_per_year),
        max_drawdown=max_drawdown(dd),
        calmar=calmar_ratio(net, dd, bars_per_year=params.bars_per_year),
        win_rate=win_rate(net),
        trade_count=trade_count_from_positions(pos),
        avg_trade_return=avg_trade_return(net, pos),
        total_turnover=float(to.sum()),
        total_cost_paid=float(cost.sum() * float(params.initial_capital)),
        benchmark_cumulative_return=bench_cum,
        alpha_vs_benchmark=alpha,
    )

    ts = dfx["timestamp"].astype(str)
    trades = _trades_from_positions(
        ts=dfx["timestamp"],
        open_px=dfx["open"] if "open" in dfx.columns else dfx["close"],
        position=pos,
        gross_return=gross,
        net_return=net,
        equity=eq,
    )
    return BacktestResult(
        summary=summary,
        equity_curve=_to_series_payload(ts, eq, "equity"),
        drawdown_curve=_to_series_payload(ts, dd, "drawdown"),
        benchmark_curve=_to_series_payload(ts, bench_eq, "equity"),
        exposure_curve=_to_series_payload(ts, pos, "exposure"),
        trades=trades,
        params=asdict(params),
    )

