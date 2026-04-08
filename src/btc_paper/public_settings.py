"""Public (non-secret) settings exposed to the Next.js dashboard."""

from __future__ import annotations

from typing import Any, Dict

from btc_paper.config import Settings


def public_settings_payload(settings: Settings) -> Dict[str, Any]:
    return {
        "paper_trade_usd": settings.paper_trade_usd,
        "take_profit_pct": settings.take_profit_pct,
        "stop_loss_pct": settings.stop_loss_pct,
        "max_hold_hours": settings.max_hold_hours,
        "news_weight": settings.news_weight,
        "technical_weight": settings.technical_weight,
        "ml_weight": settings.ml_weight,
        "legacy_news_weight": settings.legacy_news_weight,
        "legacy_technical_weight": settings.legacy_technical_weight,
        "ml_enabled": settings.ml_enabled,
        "technical_tf_1h_weight": settings.technical_tf_1h_weight,
        "technical_tf_4h_weight": settings.technical_tf_4h_weight,
        "ml_horizon_weight_1h": settings.ml_horizon_weight_1h,
        "ml_horizon_weight_12h": settings.ml_horizon_weight_12h,
        "ml_horizon_weight_24h": settings.ml_horizon_weight_24h,
        "models_dir": str(settings.models_dir),
        "backtest_defaults": {
            "buy_threshold": settings.backtest_buy_threshold,
            "sell_threshold": settings.backtest_sell_threshold,
            "fee_bps": settings.backtest_fee_bps,
            "slippage_bps": settings.backtest_slippage_bps,
            "sizing_mode": settings.backtest_sizing_mode,
            "vol_window": settings.backtest_vol_window,
            "max_position_size": settings.backtest_max_position_size,
            "target_volatility": settings.backtest_target_volatility,
            "initial_capital": settings.backtest_initial_capital,
        },
    }
