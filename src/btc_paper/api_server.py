"""JSON API for the Next.js dashboard."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import pandas as pd
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from btc_paper import db
from btc_paper.config import Settings, load_settings
from btc_paper.paper_trader import manual_order, try_rule_based_exit
from btc_paper.technical.coingecko import fetch_spot_price_usd
from btc_paper.technical.indicators import TimeframeAnalysis
from btc_paper.technical.live_analysis import compute_live_technical_with_dataframes


def _row_to_dict(row: Any) -> Dict[str, Any]:
    d = dict(row)
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _jsonable_signal_row(row: Any) -> Dict[str, Any]:
    out = _row_to_dict(row)
    raw = out.get("breakdown_json")
    if isinstance(raw, str):
        try:
            out["breakdown"] = json.loads(raw)
        except json.JSONDecodeError:
            out["breakdown"] = None
    return out


def _safe_float(val: Any) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _max_drawdown(pnls: List[float]) -> float:
    if not pnls:
        return 0.0
    equity = pd.Series(pd.Series(pnls).cumsum())
    running_max = equity.cummax()
    dd = equity - running_max
    return float(dd.min())


def _ta_to_dict(ta: Optional[TimeframeAnalysis]) -> Optional[Dict[str, Any]]:
    if ta is None:
        return None
    return {
        "timeframe": ta.timeframe,
        "score": ta.score,
        "trend": ta.trend,
        "rsi": ta.rsi,
        "rsi_signal": ta.rsi_signal,
        "bollinger_signal": ta.bollinger_signal,
        "macd_signal": ta.macd_signal,
        "volatility_high": ta.volatility_high,
        "detail": ta.detail,
    }


def _df_ohlc_tail(df: Optional[pd.DataFrame], max_points: int = 250) -> List[Dict[str, Any]]:
    if df is None or len(df) == 0:
        return []
    tail = df.tail(max_points)
    out: List[Dict[str, Any]] = []
    for idx, row in tail.iterrows():
        if hasattr(idx, "isoformat"):
            ts = idx.isoformat()  # type: ignore[union-attr]
        else:
            ts = str(idx)
        out.append(
            {
                "ts": ts,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0) or 0),
            }
        )
    return out


def _public_settings(settings: Settings) -> Dict[str, Any]:
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
    }


def _resolve_price(settings: Settings, price: Optional[float]) -> float:
    if price is not None and price > 0:
        return float(price)
    try:
        return float(fetch_spot_price_usd(settings))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400,
            detail=f"No valid price and live fetch failed: {exc}",
        ) from exc


app = FastAPI(title="AI Trading Bot Pro Max Ultra Plus 9000 API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    # Any dev port (3002, …) when NEXT_PUBLIC_API_URL points straight at FastAPI
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/settings/public")
def settings_public() -> dict[str, Any]:
    return _public_settings(load_settings())


@app.get("/api/price/live")
def price_live() -> dict[str, Any]:
    settings = load_settings()
    try:
        p = fetch_spot_price_usd(settings)
        return {"price": p, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"price": None, "error": str(exc)}


@app.get("/api/signal/latest")
def latest_signal() -> dict[str, Optional[dict[str, Any]]]:
    settings = load_settings()
    with db.connect(settings) as conn:
        row = db.fetch_latest_signal(conn)
        if row is None:
            return {"signal": None}
        return {"signal": _jsonable_signal_row(row)}


@app.get("/api/overview")
def overview() -> dict[str, Any]:
    settings = load_settings()
    live_price: Optional[float] = None
    price_warn = ""
    try:
        live_price = fetch_spot_price_usd(settings)
    except Exception as exc:  # noqa: BLE001
        price_warn = str(exc)

    with db.connect(settings) as conn:
        sig_row = db.fetch_latest_signal(conn)
        news_rows = db.fetch_recent_news(conn, 10)
        open_trade = db.get_open_paper_trade(conn)
        closed = db.fetch_closed_trades(conn, 200)
        perf = dict(db.aggregate_performance(conn))

    closed_list = [_row_to_dict(r) for r in closed]
    pnls = [_safe_float(r["pnl"]) for r in reversed(closed) if r["pnl"] is not None]
    mdd = _max_drawdown(pnls)
    win_rate = (perf["wins"] / perf["trade_count"] * 100) if perf.get("trade_count") else 0.0
    cum = list(pd.Series(pnls).cumsum()) if pnls else []
    cum_pnl_series = [{"i": i, "v": float(v)} for i, v in enumerate(cum)]

    return {
        "live_price": live_price,
        "price_warn": price_warn,
        "signal": _jsonable_signal_row(sig_row) if sig_row else None,
        "news": [_row_to_dict(r) for r in news_rows],
        "open_trade": _row_to_dict(open_trade) if open_trade else None,
        "closed_trades": closed_list,
        "performance": perf,
        "max_drawdown_usd": mdd,
        "win_rate_pct": win_rate,
        "cumulative_pnl": cum_pnl_series,
        "settings": _public_settings(settings),
    }


@app.get("/api/news")
def api_news(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    settings = load_settings()
    with db.connect(settings) as conn:
        rows = db.fetch_recent_news(conn, limit)
    return {"articles": [_row_to_dict(r) for r in rows]}


@app.get("/api/news/analytics")
def news_analytics(max_days: int = Query(90, ge=7, le=365)) -> dict[str, Any]:
    """FinBERT / sentiment summary plus daily aggregates for charts."""
    settings = load_settings()
    with db.connect(settings) as conn:
        summary = db.aggregate_news_sentiment_stats(conn)
        series = db.fetch_news_daily_aggregates(conn, max_days=max_days)
    return {
        "summary": {
            **summary,
            "finbert_model": settings.finbert_model,
        },
        "series": series,
    }


@app.post("/api/news/sync")
def news_sync() -> dict[str, Any]:
    """
    Fetch Yahoo BTC-adjacent headlines, run FinBERT, upsert SQLite — same as the News page
    refresh action and the pipeline news step.
    """
    from btc_paper.news_sync import sync_yahoo_news_to_db
    from btc_paper.sentiment.finbert import FinBERTSentiment

    settings = load_settings()
    try:
        engine = FinBERTSentiment(settings)
        ingest = sync_yahoo_news_to_db(settings, sentiment_engine=engine)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "ok": True,
        "raw_article_count": ingest.raw_article_count,
        "scored_and_stored": ingest.scored_and_stored,
        "top_headlines": ingest.top_headlines,
    }


@app.get("/api/signals/recent")
def signals_recent(n: int = Query(45, ge=1, le=500)) -> dict[str, Any]:
    settings = load_settings()
    with db.connect(settings) as conn:
        rows = db.fetch_recent_signals(conn, n)
    return {"signals": [_jsonable_signal_row(r) for r in rows]}


@app.get("/api/trades")
def api_trades(limit: int = Query(5000, ge=1, le=50_000)) -> dict[str, Any]:
    settings = load_settings()
    with db.connect(settings) as conn:
        closed = db.fetch_closed_trades(conn, limit)
        open_trade = db.get_open_paper_trade(conn)
        perf = db.aggregate_performance(conn)
    return {
        "closed": [_row_to_dict(r) for r in closed],
        "open_trade": _row_to_dict(open_trade) if open_trade else None,
        "performance": dict(perf),
    }


@app.get("/api/paper/state")
def paper_state() -> dict[str, Any]:
    settings = load_settings()
    live_px: Optional[float] = None
    live_err = ""
    try:
        live_px = fetch_spot_price_usd(settings)
    except Exception as exc:  # noqa: BLE001
        live_err = str(exc)
    with db.connect(settings) as conn:
        sig_row = db.fetch_latest_signal(conn)
        open_trade = db.get_open_paper_trade(conn)
        closed = db.fetch_closed_trades(conn, 80)
        perf = db.aggregate_performance(conn)
    signal = _jsonable_signal_row(sig_row) if sig_row else None
    br = signal.get("breakdown") if signal else None
    tech = (br or {}).get("technical") or {} if isinstance(br, dict) else {}
    return {
        "live_price": live_px,
        "live_price_error": live_err,
        "signal_price": _safe_float(sig_row["btc_price"]) if sig_row else 0.0,
        "signal": signal,
        "technical_1h": tech.get("1h"),
        "technical_4h": tech.get("4h"),
        "open_trade": _row_to_dict(open_trade) if open_trade else None,
        "closed_trades": [_row_to_dict(r) for r in closed],
        "performance": dict(perf),
        "settings": _public_settings(settings),
    }


class PaperOrderBody(BaseModel):
    intent: Literal["buy", "sell", "close"]
    usd_notional: Optional[float] = Field(default=None, gt=0)
    price: Optional[float] = Field(default=None, gt=0)


@app.post("/api/paper/order")
def paper_order(body: PaperOrderBody) -> dict[str, Any]:
    settings = load_settings()
    px = body.price if body.price and body.price > 0 else None
    if px is None:
        px = _resolve_price(settings, None)
    now = datetime.now(timezone.utc)
    with db.connect(settings) as conn:
        ok, msg = manual_order(
            conn,
            settings,
            intent=body.intent,
            price=px,
            now=now,
            usd_notional=body.usd_notional,
        )
    return {"ok": ok, "message": msg, "price_used": px}


class PriceBody(BaseModel):
    price: Optional[float] = Field(default=None, gt=0)


@app.post("/api/paper/check-exit")
def paper_check_exit(body: Optional[PriceBody] = Body(default=None)) -> dict[str, Any]:
    settings = load_settings()
    raw = body.price if body and body.price and body.price > 0 else None
    px = _resolve_price(settings, raw)
    now = datetime.now(timezone.utc)
    with db.connect(settings) as conn:
        ok, msg = try_rule_based_exit(conn, settings, price=px, now=now)
    return {"ok": ok, "message": msg, "price_used": px}


@app.get("/api/ml/summary")
def ml_summary(hist_n: int = Query(45, ge=5, le=200)) -> dict[str, Any]:
    settings = load_settings()
    root = Path.cwd()
    mdir = settings.models_dir if settings.models_dir.is_absolute() else root / settings.models_dir
    meta_path = mdir / "model_metadata.json"
    metadata: Optional[dict[str, Any]] = None
    if meta_path.exists():
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = None

    with db.connect(settings) as conn:
        sig_latest = db.fetch_latest_signal(conn)
        sig_rows = db.fetch_recent_signals(conn, hist_n)

    hist: List[dict[str, Any]] = []
    for r in reversed(sig_rows):
        rowd = _jsonable_signal_row(r)
        br = rowd.get("breakdown") or {}
        if not isinstance(br, dict):
            br = {}
        ml = br.get("ml") or {}
        hp2 = ml.get("horizon_predictions") or {}
        hist.append(
            {
                "run_at": rowd.get("run_at"),
                "action": rowd.get("action"),
                "final_score": _safe_float(rowd.get("final_score")),
                "ml_score": _safe_float(br.get("ml_score", 0)),
                "ml_prob": _safe_float(ml.get("ml_prob")) if ml.get("ml_prob") is not None else None,
                "p_1h": _safe_float((hp2.get("target_up_1h") or {}).get("prob_up"))
                if hp2.get("target_up_1h")
                else None,
                "p_12h": _safe_float((hp2.get("target_up_12h") or {}).get("prob_up"))
                if hp2.get("target_up_12h")
                else None,
                "p_24h": _safe_float((hp2.get("target_up_24h") or {}).get("prob_up"))
                if hp2.get("target_up_24h")
                else None,
                "ml_bias": ml.get("ml_bias"),
            }
        )

    latest = _jsonable_signal_row(sig_latest) if sig_latest else None
    breakdown = latest.get("breakdown") if latest else None
    if not isinstance(breakdown, dict):
        breakdown = {}
    ml_block = breakdown.get("ml")
    weights = breakdown.get("weights")

    return {
        "metadata": metadata,
        "meta_path": str(meta_path),
        "latest_signal": latest,
        "ml_block": ml_block,
        "weights": weights,
        "conflict_dampened": bool(breakdown.get("conflict_dampened")),
        "reason": latest.get("reason") if latest else None,
        "history": hist,
        "settings": _public_settings(settings),
    }


@app.get("/api/technical/live")
def technical_live(chart_points: int = Query(200, ge=20, le=500)) -> dict[str, Any]:
    settings = load_settings()
    report, df_1h, df_4h = compute_live_technical_with_dataframes(settings)
    return {
        "spot_usd": report.spot_usd,
        "spot_error": report.spot_error,
        "spot_source": report.spot_source,
        "series_1h_candles": report.series_1h_candles,
        "series_1h_start": report.series_1h_start,
        "series_1h_end": report.series_1h_end,
        "series_4h_candles": report.series_4h_candles,
        "series_4h_start": report.series_4h_start,
        "series_4h_end": report.series_4h_end,
        "err_1h": report.err_1h,
        "err_4h": report.err_4h,
        "ta_1h": _ta_to_dict(report.ta_1h),
        "ta_4h": _ta_to_dict(report.ta_4h),
        "weight_1h": report.weight_1h,
        "weight_4h": report.weight_4h,
        "technical_score": report.technical_score,
        "blend_explanation": report.blend_explanation,
        "chart_1h": _df_ohlc_tail(df_1h, chart_points),
        "chart_4h": _df_ohlc_tail(df_4h, chart_points),
    }


@app.get("/api/market/analysis")
def market_analysis(
    sig_limit: int = Query(120, ge=10, le=500),
    candle_bars: int = Query(200, ge=20, le=500),
    news_limit: int = Query(400, ge=10, le=1000),
) -> dict[str, Any]:
    settings = load_settings()
    with db.connect(settings) as conn:
        sig_rows = db.fetch_recent_signals(conn, sig_limit)
        news_rows = db.fetch_recent_news(conn, news_limit)
        c_1h = db.fetch_candles_recent(conn, timeframe="1h", max_bars=candle_bars)
        c_4h = db.fetch_candles_recent(conn, timeframe="4h", max_bars=candle_bars)
    signals = [_jsonable_signal_row(r) for r in reversed(sig_rows)]
    return {
        "signals": signals,
        "candles_1h": [_row_to_dict(r) for r in c_1h],
        "candles_4h": [_row_to_dict(r) for r in c_4h],
        "news": [_row_to_dict(r) for r in news_rows],
    }


def main() -> None:
    import uvicorn

    host = os.environ.get("API_HOST", "127.0.0.1")
    port = int(os.environ.get("API_PORT", "8000"))
    uvicorn.run("btc_paper.api_server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
