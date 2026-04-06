"""Canonical ML feature column order — must match training, inference, and export."""

from __future__ import annotations

FEATURE_COLUMNS: list[str] = [
    "news_score",
    "technical_score",
    "final_rule_score",
    "ema_trend_1h",
    "ema_trend_4h",
    "rsi_1h",
    "rsi_4h",
    "bollinger_position_1h",
    "bollinger_position_4h",
    "bollinger_width_1h",
    "bollinger_width_4h",
    "macd_score_1h",
    "macd_score_4h",
    "return_1h",
    "return_4h",
    "volume_change_1h",
    "volume_change_4h",
    "price_close",
]

FEATURE_VERSION = "1.0"
