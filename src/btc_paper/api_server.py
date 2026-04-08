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
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from btc_paper import db
from btc_paper.config import Settings, load_settings
from btc_paper.overview_data import build_overview_payload
from btc_paper.public_settings import public_settings_payload
from btc_paper import snapshots as snap
from btc_paper.paper_trader import manual_order, try_rule_based_exit
from btc_paper.technical.coingecko import fetch_spot_price_usd
from btc_paper.technical.indicators import TimeframeAnalysis
from btc_paper.technical.live_analysis import compute_live_technical_with_dataframes
from btc_paper.backtest.dataset import generate_backtest_dataset
from btc_paper.backtest.engine import run_backtest
from btc_paper.backtest.schemas import BacktestParams


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


def _reject_heavy_if_blocked(settings: Settings) -> None:
    """Block pandas backtests on lean deploy hosts (set BLOCK_HEAVY_COMPUTE=true)."""
    if settings.block_heavy_compute:
        raise HTTPException(
            status_code=503,
            detail="Heavy compute is disabled (BLOCK_HEAVY_COMPUTE). Use SNAPSHOT_MODE with pre-exported files.",
        )


def _signal_position_from_action(action: str) -> str:
    a = (action or "").upper()
    if a == "BUY":
        return "LONG"
    if a == "SELL":
        return "SHORT"
    return "FLAT"


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


def _cors_allow_origins() -> List[str]:
    """Local dev defaults plus optional production origins (Render, Vercel, etc.)."""
    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if raw:
        for part in raw.split(","):
            o = part.strip().rstrip("/")
            if o and o not in origins:
                origins.append(o)
    single = os.environ.get("FRONTEND_URL", "").strip().rstrip("/")
    if single and single not in origins:
        origins.append(single)
    return origins


app = FastAPI(title="AI Trading Bot Pro Max Ultra Plus 9000 API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    # Any dev port (3002, …) when NEXT_PUBLIC_API_URL points straight at FastAPI
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> RedirectResponse:
    """Bare domain (e.g. Render) → interactive API docs (avoids FastAPI’s default 404 on `/`)."""
    return RedirectResponse(url="/docs", status_code=307)


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/settings/public")
def settings_public() -> dict[str, Any]:
    settings = load_settings()
    if settings.snapshot_mode:
        try:
            return snap.settings_public_snapshot(settings)
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail=f"Snapshot settings failed: {exc}") from exc
    out = public_settings_payload(settings)
    out["demo_snapshot"] = snap.demo_snapshot_flags(settings)
    return out


@app.get("/api/price/live")
def price_live() -> dict[str, Any]:
    settings = load_settings()
    if settings.snapshot_mode:
        try:
            market = snap.load_market_snapshot(settings)
            p = market.get("price")
            return {"price": p, "error": None}
        except FileNotFoundError as exc:
            return {"price": None, "error": str(exc)}
        except (OSError, json.JSONDecodeError) as exc:
            return {"price": None, "error": f"Snapshot market failed: {exc}"}
    try:
        p = fetch_spot_price_usd(settings)
        return {"price": p, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"price": None, "error": str(exc)}


@app.get("/api/signal/latest")
def latest_signal() -> dict[str, Optional[dict[str, Any]]]:
    settings = load_settings()
    if settings.snapshot_mode:
        try:
            return snap.load_latest_signal_snapshot(settings)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail=f"Snapshot signal failed: {exc}") from exc
    with db.connect(settings) as conn:
        row = db.fetch_latest_signal(conn)
        if row is None:
            return {"signal": None}
        return {"signal": _jsonable_signal_row(row)}


@app.get("/api/overview")
def overview() -> dict[str, Any]:
    settings = load_settings()
    if settings.snapshot_mode:
        try:
            return snap.load_overview_snapshot(settings)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail=f"Snapshot overview failed: {exc}") from exc
    return build_overview_payload(settings, fetch_live_price=True)


@app.get("/api/news")
def api_news(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    settings = load_settings()
    if settings.snapshot_mode:
        try:
            data = snap.load_news_snapshot(settings, limit)
            return {"articles": data.get("articles") or []}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail=f"Snapshot news failed: {exc}") from exc
    with db.connect(settings) as conn:
        rows = db.fetch_recent_news(conn, limit)
    return {"articles": [_row_to_dict(r) for r in rows]}


@app.get("/api/news/analytics")
def news_analytics(max_days: int = Query(90, ge=7, le=365)) -> dict[str, Any]:
    """FinBERT / sentiment summary plus daily aggregates for charts."""
    settings = load_settings()
    if settings.snapshot_mode:
        try:
            data = snap.load_news_snapshot(settings, limit=500)
            analytics = data.get("analytics") or {}
            # Ensure stable shape for the frontend.
            return {
                "summary": analytics.get("summary")
                or {
                    "articles_scored": 0,
                    "avg_finbert_sentiment_score": None,
                    "avg_weighted_article_score": None,
                    "avg_confidence": None,
                    "label_counts": {"bullish": 0, "bearish": 0, "neutral": 0},
                    "finbert_model": settings.finbert_model,
                },
                "series": analytics.get("series") or [],
            }
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail=f"Snapshot news analytics failed: {exc}") from exc
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
    if settings.snapshot_mode:
        raise HTTPException(
            status_code=503,
            detail="News sync is disabled in SNAPSHOT_MODE. Refresh snapshots locally and redeploy.",
        )
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
    if settings.snapshot_mode:
        try:
            return snap.load_signals_recent_snapshot(settings, n)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail=f"Snapshot signals failed: {exc}") from exc
    with db.connect(settings) as conn:
        rows = db.fetch_recent_signals(conn, n)
    return {"signals": [_jsonable_signal_row(r) for r in rows]}


@app.get("/api/trades")
def api_trades(limit: int = Query(5000, ge=1, le=50_000)) -> dict[str, Any]:
    settings = load_settings()
    if settings.snapshot_mode:
        try:
            return snap.load_trades_snapshot(settings, limit)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail=f"Snapshot trades failed: {exc}") from exc
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
    if settings.snapshot_mode:
        try:
            return snap.load_paper_state_snapshot(settings)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=f"Snapshot paper state failed: {exc}") from exc
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
        "settings": public_settings_payload(settings),
    }


class PaperOrderBody(BaseModel):
    intent: Literal["buy", "sell", "close"]
    usd_notional: Optional[float] = Field(default=None, gt=0)
    price: Optional[float] = Field(default=None, gt=0)


@app.post("/api/paper/order")
def paper_order(body: PaperOrderBody) -> dict[str, Any]:
    settings = load_settings()
    if settings.snapshot_mode:
        raise HTTPException(
            status_code=503,
            detail="Paper trading is read-only in SNAPSHOT_MODE.",
        )
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
    if settings.snapshot_mode:
        raise HTTPException(
            status_code=503,
            detail="Paper trading is read-only in SNAPSHOT_MODE.",
        )
    raw = body.price if body and body.price and body.price > 0 else None
    px = _resolve_price(settings, raw)
    now = datetime.now(timezone.utc)
    with db.connect(settings) as conn:
        ok, msg = try_rule_based_exit(conn, settings, price=px, now=now)
    return {"ok": ok, "message": msg, "price_used": px}


@app.get("/api/history")
def api_history(
    ml_limit: int = Query(500, ge=1, le=5000),
    sig_limit: int = Query(500, ge=1, le=5000),
) -> dict[str, Any]:
    """Chart-friendly series: precomputed CSV in snapshot mode, else built from recent signals."""
    settings = load_settings()
    if settings.snapshot_mode:
        return snap.load_history_snapshot(settings, ml_limit, sig_limit)
    n = max(ml_limit, sig_limit)
    with db.connect(settings) as conn:
        rows = db.fetch_recent_signals(conn, n)
    chron = list(reversed(rows))
    ml_predictions: List[dict[str, Any]] = []
    for r in chron[-ml_limit:]:
        rowd = _jsonable_signal_row(r)
        br = rowd.get("breakdown") or {}
        if not isinstance(br, dict):
            br = {}
        ml = br.get("ml") or {}
        hp = ml.get("horizon_predictions") or {}
        p1 = (hp.get("target_up_1h") or {}).get("prob_up")
        p12 = (hp.get("target_up_12h") or {}).get("prob_up")
        p24 = (hp.get("target_up_24h") or {}).get("prob_up")
        ml_predictions.append(
            {
                "timestamp": rowd.get("run_at"),
                "prediction": ml.get("ml_bias") or "",
                "probability": ml.get("ml_prob"),
                "prob_1h": p1,
                "prob_12h": p12,
                "prob_24h": p24,
                "ml_score": br.get("ml_score", 0),
                "final_score": rowd.get("final_score"),
                "action": rowd.get("action"),
            }
        )
    signal_points: List[dict[str, Any]] = []
    for r in rows[:sig_limit]:
        rowd = _jsonable_signal_row(r)
        signal_points.append(
            {
                "timestamp": rowd.get("run_at"),
                "final_score": _safe_float(rowd.get("final_score")),
                "position": _signal_position_from_action(str(rowd.get("action", ""))),
                "action": rowd.get("action"),
            }
        )
    return {"ml_predictions": ml_predictions, "signal_points": signal_points}


@app.get("/api/ml/summary")
def ml_summary(hist_n: int = Query(45, ge=5, le=200)) -> dict[str, Any]:
    settings = load_settings()
    if settings.snapshot_mode:
        try:
            return snap.load_ml_summary_snapshot(settings, hist_n)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=f"Snapshot ML summary failed: {exc}") from exc
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
        "settings": public_settings_payload(settings),
    }


@app.get("/api/technical/live")
def technical_live(chart_points: int = Query(200, ge=20, le=500)) -> dict[str, Any]:
    settings = load_settings()
    if settings.snapshot_mode:
        try:
            return snap.load_technical_snapshot(settings)
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail=f"Snapshot technical failed: {exc}") from exc
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
    if settings.snapshot_mode:
        frozen = snap.load_market_analysis_snapshot(settings)
        if frozen is not None:
            return frozen
        return {"signals": [], "candles_1h": [], "candles_4h": [], "news": []}
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


@app.get("/api/backtest/run")
def backtest_run(
    sizing_mode: str = Query("confidence"),
    buy_threshold: float = Query(0.08),
    sell_threshold: float = Query(-0.08),
    fee_bps: float = Query(0.0, ge=0),
    slippage_bps: float = Query(0.0, ge=0),
    vol_window: int = Query(72, ge=2, le=2000),
    max_position_size: float = Query(1.0, ge=0, le=5),
    target_volatility: float = Query(0.20, ge=0, le=5),
    initial_capital: float = Query(10_000.0, gt=0),
    reconstruct_signal: bool = Query(False),
    news_lookback_hours: int = Query(24, ge=1, le=240),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
) -> dict[str, Any]:
    """
    Run a default quant-style backtest on historical bars using stored `final_score`.
    Signal at bar t -> executed position at bar t+1 (no lookahead).
    """
    settings = load_settings()
    if settings.snapshot_mode:
        try:
            return snap.load_backtest_run_snapshot(settings)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail=f"Snapshot backtest failed: {exc}") from exc
    _reject_heavy_if_blocked(settings)
    params = BacktestParams(
        sizing_mode=sizing_mode,  # validated inside sizing module
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        vol_window=vol_window,
        max_position_size=max_position_size,
        target_volatility=target_volatility,
        initial_capital=initial_capital,
        start_iso=start_date,
        end_iso=end_date,
    )
    ds = generate_backtest_dataset(
        settings,
        start_iso=start_date,
        end_iso=end_date,
        reconstruct_signal=reconstruct_signal,
        news_lookback_hours=news_lookback_hours,
    )
    res = run_backtest(ds.df, params)
    score_curve: list[dict[str, Any]] = []
    if ds.df is not None and len(ds.df) > 0 and "timestamp" in ds.df.columns and "final_score" in ds.df.columns:
        for _ts, _s in zip(ds.df["timestamp"].tolist(), ds.df["final_score"].astype(float).tolist()):
            ts_str = _ts.isoformat() if hasattr(_ts, "isoformat") else str(_ts)
            score_curve.append({"ts": ts_str, "final_score": float(_s)})
    return {
        "summary": res.summary.__dict__,
        "equity_curve": res.equity_curve,
        "drawdown_curve": res.drawdown_curve,
        "benchmark_curve": res.benchmark_curve,
        "exposure_curve": res.exposure_curve,
        "score_curve": score_curve,
        "trades": res.trades,
        "params": res.params,
        "dataset_source": ds.source,
        "bars": len(ds.df),
    }


@app.get("/api/backtest/trades")
def backtest_trades(
    sizing_mode: str = Query("confidence"),
    buy_threshold: float = Query(0.08),
    sell_threshold: float = Query(-0.08),
    fee_bps: float = Query(0.0, ge=0),
    slippage_bps: float = Query(0.0, ge=0),
    vol_window: int = Query(72, ge=2, le=2000),
    max_position_size: float = Query(1.0, ge=0, le=5),
    target_volatility: float = Query(0.20, ge=0, le=5),
    initial_capital: float = Query(10_000.0, gt=0),
    reconstruct_signal: bool = Query(False),
    news_lookback_hours: int = Query(24, ge=1, le=240),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
) -> dict[str, Any]:
    settings = load_settings()
    if settings.snapshot_mode:
        try:
            data = snap.load_backtest_run_snapshot(settings)
            return {
                "trades": data.get("trades", []),
                "params": data.get("params", {}),
                "bars": int(data.get("bars", 0) or 0),
            }
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail=f"Snapshot backtest trades failed: {exc}") from exc
    _reject_heavy_if_blocked(settings)
    params = BacktestParams(
        sizing_mode=sizing_mode,
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        vol_window=vol_window,
        max_position_size=max_position_size,
        target_volatility=target_volatility,
        initial_capital=initial_capital,
        start_iso=start_date,
        end_iso=end_date,
    )
    ds = generate_backtest_dataset(
        settings,
        start_iso=start_date,
        end_iso=end_date,
        reconstruct_signal=reconstruct_signal,
        news_lookback_hours=news_lookback_hours,
    )
    res = run_backtest(ds.df, params)
    return {"trades": res.trades, "params": res.params, "bars": len(ds.df)}


@app.get("/api/backtest/compare")
def backtest_compare(
    buy_threshold: float = Query(0.35),
    sell_threshold: float = Query(-0.35),
    fee_bps: float = Query(0.0, ge=0),
    slippage_bps: float = Query(0.0, ge=0),
    vol_window: int = Query(72, ge=2, le=2000),
    max_position_size: float = Query(1.0, ge=0, le=5),
    target_volatility: float = Query(0.20, ge=0, le=5),
    initial_capital: float = Query(10_000.0, gt=0),
    reconstruct_signal: bool = Query(False),
    news_lookback_hours: int = Query(24, ge=1, le=240),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
) -> dict[str, Any]:
    """
    Compare sizing modes side by side (fixed vs confidence vs vol-adjusted).
    """
    settings = load_settings()
    if settings.snapshot_mode:
        try:
            return snap.load_backtest_compare_snapshot(settings)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"{exc}. Run btc-paper-export-snapshots to generate backtest_compare.json.",
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail=f"Snapshot compare failed: {exc}") from exc
    _reject_heavy_if_blocked(settings)
    ds = generate_backtest_dataset(
        settings,
        start_iso=start_date,
        end_iso=end_date,
        reconstruct_signal=reconstruct_signal,
        news_lookback_hours=news_lookback_hours,
    )
    modes = ["fixed", "confidence", "confidence_vol"]
    results: list[dict[str, Any]] = []
    curves: dict[str, Any] = {}
    for m in modes:
        params = BacktestParams(
            sizing_mode=m,
            buy_threshold=buy_threshold,
            sell_threshold=sell_threshold,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            vol_window=vol_window,
            max_position_size=max_position_size,
            target_volatility=target_volatility,
            initial_capital=initial_capital,
            start_iso=start_date,
            end_iso=end_date,
        )
        res = run_backtest(ds.df, params)
        results.append({"sizing_mode": m, **res.summary.__dict__})
        curves[m] = res.equity_curve
    return {
        "metrics": results,
        "equity_curves": curves,
        "benchmark_curve": run_backtest(ds.df, BacktestParams(initial_capital=initial_capital)).benchmark_curve,
        "bars": len(ds.df),
        "dataset_source": ds.source,
    }


@app.get("/api/backtest/walkforward")
def backtest_walkforward(
    train_bars: int = Query(24 * 30, ge=24 * 7, le=24 * 365),
    test_bars: int = Query(24 * 7, ge=24, le=24 * 90),
    step_bars: int = Query(24 * 7, ge=24, le=24 * 90),
    sizing_mode: str = Query("fixed"),
    buy_threshold: float = Query(0.35),
    sell_threshold: float = Query(-0.35),
    fee_bps: float = Query(0.0, ge=0),
    slippage_bps: float = Query(0.0, ge=0),
    vol_window: int = Query(72, ge=2, le=2000),
    max_position_size: float = Query(1.0, ge=0, le=5),
    target_volatility: float = Query(0.20, ge=0, le=5),
    initial_capital: float = Query(10_000.0, gt=0),
    reconstruct_signal: bool = Query(False),
    news_lookback_hours: int = Query(24, ge=1, le=240),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
) -> dict[str, Any]:
    """
    Walk-forward evaluation on historical `final_score` without retraining models (first pass).

    For each window:
    - Use the next `test_bars` as out-of-sample evaluation segment.
    - Concatenate OOS segments into one continuous curve.
    """
    settings = load_settings()
    if settings.snapshot_mode:
        try:
            return snap.load_backtest_walkforward_snapshot(settings)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"{exc}. Run btc-paper-export-snapshots to generate backtest_walkforward.json.",
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail=f"Snapshot walk-forward failed: {exc}") from exc
    _reject_heavy_if_blocked(settings)
    ds = generate_backtest_dataset(
        settings,
        start_iso=start_date,
        end_iso=end_date,
        reconstruct_signal=reconstruct_signal,
        news_lookback_hours=news_lookback_hours,
    )
    df = ds.df
    if df is None or len(df) == 0:
        return {"summary": None, "equity_curve": [], "windows": [], "bars": 0, "dataset_source": ds.source}

    params_base = BacktestParams(
        sizing_mode=sizing_mode,
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        vol_window=vol_window,
        max_position_size=max_position_size,
        target_volatility=target_volatility,
        initial_capital=initial_capital,
        start_iso=start_date,
        end_iso=end_date,
    )

    windows: list[dict[str, Any]] = []
    oos_parts: list[dict[str, Any]] = []
    eq0 = float(initial_capital)

    i = 0
    while True:
        train_end = i + train_bars
        test_end = train_end + test_bars
        if test_end > len(df):
            break
        test_df = df.iloc[train_end:test_end].copy()
        # Run backtest on test slice; rebase equity to current eq0 for continuity
        params = BacktestParams(**{**params_base.__dict__, "initial_capital": eq0})
        res = run_backtest(test_df, params)
        if res.equity_curve:
            eq0 = float(res.equity_curve[-1]["equity"])  # type: ignore[index]
        windows.append(
            {
                "train_start": str(df.iloc[i]["timestamp"]),
                "train_end": str(df.iloc[train_end - 1]["timestamp"]),
                "test_start": str(test_df.iloc[0]["timestamp"]),
                "test_end": str(test_df.iloc[-1]["timestamp"]),
                "summary": res.summary.__dict__,
            }
        )
        oos_parts.extend(res.equity_curve)
        i += step_bars

    # Summary on concatenated curve (approx): use last eq vs initial_capital
    summary = None
    if oos_parts:
        last_eq = float(oos_parts[-1]["equity"])  # type: ignore[index]
        summary = {
            "oos_cumulative_return": (last_eq / float(initial_capital)) - 1.0,
            "windows": len(windows),
        }
    return {
        "summary": summary,
        "equity_curve": oos_parts,
        "windows": windows,
        "bars": len(df),
        "dataset_source": ds.source,
        "params": params_base.__dict__,
    }


def main() -> None:
    import uvicorn

    # Render (and similar) set PORT and require binding 0.0.0.0 for inbound traffic.
    if os.environ.get("PORT"):
        host = os.environ.get("API_HOST", "0.0.0.0")
        port = int(os.environ["PORT"])
    else:
        host = os.environ.get("API_HOST", "127.0.0.1")
        port = int(os.environ.get("API_PORT", "8000"))
    uvicorn.run("btc_paper.api_server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
