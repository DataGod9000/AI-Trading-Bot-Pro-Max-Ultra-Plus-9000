from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_path: Path = Field(default=Path("data/bot.db"), validation_alias="DATABASE_PATH")
    reports_dir: Path = Field(default=Path("reports"), validation_alias="REPORTS_DIR")
    raw_news_dir: Path = Field(default=Path("data/raw_news"), validation_alias="RAW_NEWS_DIR")
    paper_trade_usd: float = Field(default=100.0, gt=0, validation_alias="PAPER_TRADE_USD")
    coingecko_base_url: str = Field(
        default="https://api.coingecko.com/api/v3",
        validation_alias="COINGECKO_BASE_URL",
    )
    # Buffers repeated API / UI requests against CoinGecko free-tier 429s.
    coingecko_cache_enabled: bool = Field(default=True, validation_alias="COINGECKO_CACHE_ENABLED")
    coingecko_cache_ttl_seconds: int = Field(default=120, ge=0, validation_alias="COINGECKO_CACHE_TTL")
    coingecko_max_retries: int = Field(default=5, ge=1, le=12, validation_alias="COINGECKO_MAX_RETRIES")
    finbert_model: str = Field(default="ProsusAI/finbert", validation_alias="FINBERT_MODEL")

    news_lookback_hours: int = 24
    signal_buy_threshold: float = 0.35
    signal_sell_threshold: float = -0.35
    # Three-way blend when ML models are loaded (PRD §6.3).
    news_weight: float = Field(default=0.3, validation_alias="SIGNAL_NEWS_WEIGHT")
    technical_weight: float = Field(default=0.3, validation_alias="SIGNAL_TECH_WEIGHT")
    ml_weight: float = Field(default=0.4, validation_alias="SIGNAL_ML_WEIGHT")
    # Classic two-way blend when ML is off or artifacts missing (preserves pre-ML behavior).
    legacy_news_weight: float = Field(default=0.6, validation_alias="LEGACY_NEWS_WEIGHT")
    legacy_technical_weight: float = Field(default=0.4, validation_alias="LEGACY_TECH_WEIGHT")
    # Used only in `final_rule_score` ML feature column (training / inference schema).
    ml_rule_news_weight: float = Field(default=0.6, validation_alias="ML_RULE_NEWS_WEIGHT")
    ml_rule_technical_weight: float = Field(default=0.4, validation_alias="ML_RULE_TECH_WEIGHT")
    ml_enabled: bool = Field(default=True, validation_alias="ML_ENABLED")
    models_dir: Path = Field(default=Path("models"), validation_alias="MODELS_DIR")
    ml_horizon_weight_1h: float = Field(default=0.2, validation_alias="ML_HORIZON_W_1H")
    ml_horizon_weight_12h: float = Field(default=0.4, validation_alias="ML_HORIZON_W_12H")
    ml_horizon_weight_24h: float = Field(default=0.4, validation_alias="ML_HORIZON_W_24H")
    signal_conflict_dampen: float = Field(default=0.7, validation_alias="SIGNAL_CONFLICT_DAMPEN")
    signal_disagreement_edge: float = Field(default=0.2, validation_alias="SIGNAL_DISAGREE_EDGE")
    technical_tf_1h_weight: float = 0.4
    technical_tf_4h_weight: float = 0.6

    # -----------------------------
    # Backtesting (quant evaluation)
    # -----------------------------
    backtest_buy_threshold: float = Field(default=0.08, validation_alias="BACKTEST_BUY_THRESHOLD")
    backtest_sell_threshold: float = Field(default=-0.08, validation_alias="BACKTEST_SELL_THRESHOLD")
    backtest_fee_bps: float = Field(default=0.0, ge=0, validation_alias="BACKTEST_FEE_BPS")
    backtest_slippage_bps: float = Field(default=0.0, ge=0, validation_alias="BACKTEST_SLIPPAGE_BPS")
    backtest_sizing_mode: str = Field(default="confidence", validation_alias="BACKTEST_SIZING_MODE")
    backtest_vol_window: int = Field(default=72, ge=2, validation_alias="BACKTEST_VOL_WINDOW")
    backtest_max_position_size: float = Field(default=1.0, ge=0, validation_alias="BACKTEST_MAX_POSITION_SIZE")
    backtest_target_volatility: float = Field(default=0.20, ge=0, validation_alias="BACKTEST_TARGET_VOLATILITY")
    backtest_initial_capital: float = Field(default=10_000.0, gt=0, validation_alias="BACKTEST_INITIAL_CAPITAL")

    take_profit_pct: float = 2.0
    stop_loss_pct: float = 1.5
    max_hold_hours: int = 24


def load_settings() -> Settings:
    return Settings()
