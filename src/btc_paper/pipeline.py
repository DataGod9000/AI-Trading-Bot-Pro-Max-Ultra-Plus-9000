from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from btc_paper import db
from btc_paper.config import Settings, load_settings
from btc_paper.paper_trader import apply_signal
from btc_paper.reports.markdown_report import write_daily_report
from btc_paper.news_sync import sync_yahoo_news_to_db
from btc_paper.sentiment.finbert import aggregate_news_score
from btc_paper.ml.features_live import build_live_ml_feature_row
from btc_paper.ml.ml_signal_engine import try_ml_predict
from btc_paper.signal_engine import combine_scores
from btc_paper.technical.coingecko import (
    fetch_market_chart_hourly,
    fetch_ohlc,
    fetch_spot_price_usd,
    ohlc_to_rows,
)
from btc_paper.technical.indicators import (
    TimeframeAnalysis,
    analysis_to_breakdown_payload,
    analyze_timeframe,
    build_df_from_rows,
    resample_ohlc,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hourly_points_to_rows(points: List[tuple]) -> List[tuple]:
    rows: List[tuple] = []
    for ts, px in points:
        rows.append((ts, px, px, px, px, 0.0))
    return rows


def _df_to_candle_rows(df) -> List[tuple]:
    rows: List[tuple] = []
    has_vol = "volume" in df.columns
    for idx, row in df.iterrows():
        vol = 0.0
        if has_vol:
            v = row["volume"]
            if not pd.isna(v):
                vol = float(v)
        rows.append(
            (
                int(idx.timestamp()),
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                vol,
            )
        )
    return rows


def _safe_analyze(df, label: str) -> Optional[TimeframeAnalysis]:
    if df is None or len(df) < 60:
        return None
    try:
        return analyze_timeframe(df, label)
    except Exception:  # noqa: BLE001
        return None


def run_pipeline(settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or load_settings()
    now = _utc_now()
    summary: Dict[str, Any] = {"run_at": now.isoformat()}

    ingest = sync_yahoo_news_to_db(settings, scraped_at=now)
    article_scores = ingest.article_scores
    top_headlines = ingest.top_headlines
    articles_count = ingest.raw_article_count

    with db.connect(settings) as conn:
        news_score = aggregate_news_score(article_scores)
        btc_price = fetch_spot_price_usd(settings)
        summary["btc_price"] = btc_price

        tech_parts: Dict[str, Any] = {}
        ta_1h: Optional[TimeframeAnalysis] = None
        ta_4h: Optional[TimeframeAnalysis] = None
        df_1h: Optional[pd.DataFrame] = None
        df_4h: Optional[pd.DataFrame] = None

        try:
            hourly = fetch_market_chart_hourly(settings, days=30)
            df_1h = build_df_from_rows(_hourly_points_to_rows(hourly))
            db.replace_candles(conn, "1h", _df_to_candle_rows(df_1h))
            ta_1h = _safe_analyze(df_1h, "1h")
        except Exception as exc:  # noqa: BLE001
            tech_parts["1h_error"] = str(exc)

        try:
            raw_30 = fetch_ohlc(settings, days=30)
            df_4h = build_df_from_rows(ohlc_to_rows(raw_30))
            db.replace_candles(conn, "4h", _df_to_candle_rows(df_4h))
            ta_4h = _safe_analyze(df_4h, "4h")
        except Exception as exc:  # noqa: BLE001
            tech_parts["4h_error"] = str(exc)

        if ta_1h and ta_4h:
            technical_score = (
                settings.technical_tf_1h_weight * ta_1h.score
                + settings.technical_tf_4h_weight * ta_4h.score
            )
            technical_summary = (
                f"1h {ta_1h.score:+.2f} (trend {ta_1h.trend}, RSI {ta_1h.rsi:.1f}, "
                f"MACD {ta_1h.macd_signal:+.2f}, vol {ta_1h.volatility_high}); "
                f"4h {ta_4h.score:+.2f} (trend {ta_4h.trend}, RSI {ta_4h.rsi:.1f})."
            )
            tech_parts["1h"] = analysis_to_breakdown_payload(ta_1h)
            tech_parts["4h"] = analysis_to_breakdown_payload(ta_4h)
        elif ta_1h:
            technical_score = ta_1h.score
            technical_summary = f"1h only {ta_1h.score:+.2f} (trend {ta_1h.trend}, RSI {ta_1h.rsi:.1f})."
            tech_parts["1h"] = analysis_to_breakdown_payload(ta_1h)
        elif ta_4h:
            technical_score = ta_4h.score
            technical_summary = f"4h only {ta_4h.score:+.2f} (trend {ta_4h.trend}, RSI {ta_4h.rsi:.1f})."
            tech_parts["4h"] = analysis_to_breakdown_payload(ta_4h)
        else:
            technical_score = 0.0
            technical_summary = "Insufficient candle data; technical score 0."

        news_summary = f"{articles_count} articles; aggregate news score {news_score:+.3f}"
        px = float(btc_price) if btc_price is not None else 0.0
        ml_feature_row = build_live_ml_feature_row(
            settings,
            news_score=news_score,
            technical_score=technical_score,
            ta_1h=ta_1h,
            ta_4h=ta_4h,
            df_1h=df_1h,
            df_4h=df_4h,
            btc_price=px,
        )
        ml_payload = try_ml_predict(settings, ml_feature_row) if settings.ml_enabled else None
        ml_active = ml_payload is not None
        ml_score = float(ml_payload["ml_score"]) if ml_payload else 0.0

        sig = combine_scores(
            settings,
            news_score=news_score,
            technical_score=technical_score,
            news_summary=news_summary,
            technical_summary=technical_summary,
            ml_score=ml_score,
            ml_active=ml_active,
            ml_payload=ml_payload,
        )
        breakdown = {
            **sig.breakdown,
            "technical": tech_parts,
            "top_headlines": top_headlines,
            "article_count": articles_count,
            "ml_feature_row": ml_feature_row,
        }
        signal_id = db.insert_signal(
            conn,
            run_at=now,
            btc_price=btc_price,
            news_score=news_score,
            technical_score=technical_score,
            final_score=sig.final_score,
            action=sig.action,
            confidence=sig.confidence,
            reason=sig.reason,
            breakdown=breakdown,
        )

        trade_id, trade_note = apply_signal(
            conn,
            settings,
            signal_id=signal_id,
            action=sig.action,
            price=btc_price,
            now=now,
        )

        open_row = db.get_open_paper_trade(conn)
        if open_row is not None:
            side = str(open_row["side"])
            entry = float(open_row["entry_price"])
            qty = float(open_row["qty"])
            unreal = (btc_price - entry) * qty if side == "BUY" else (entry - btc_price) * qty
            trade_panel = (
                f"Open {side} @ {entry:,.2f} (qty {qty:.6f} BTC). "
                f"Mark {btc_price:,.2f}. Unrealized PnL ${unreal:,.2f}. ({trade_note})"
            )
        else:
            trade_panel = f"Flat. Last action: {trade_note}"

        write_daily_report(
            settings,
            run_at=now,
            btc_price=btc_price,
            headlines=top_headlines,
            news_score=news_score,
            technical_score=technical_score,
            ml_score=ml_score if ml_active else None,
            final_score=sig.final_score,
            action=sig.action,
            confidence=sig.confidence,
            reason=sig.reason,
            technical_notes=technical_summary + "\n\n```json\n" + json.dumps(tech_parts, indent=2) + "\n```",
            trade_note=trade_panel,
        )

        summary.update(
            {
                "signal_id": signal_id,
                "action": sig.action,
                "final_score": sig.final_score,
                "news_score": news_score,
                "technical_score": technical_score,
                "ml_score": ml_score,
                "ml_active": ml_active,
                "trade_id": trade_id,
                "trade_note": trade_note,
            }
        )

    return summary
