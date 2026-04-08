"""Build the `/api/overview` JSON payload from the database (shared with snapshot export)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pandas as pd

from btc_paper import db
from btc_paper.config import Settings
from btc_paper.technical.coingecko import fetch_spot_price_usd


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


def build_overview_payload(settings: Settings, *, fetch_live_price: bool = True) -> Dict[str, Any]:
    """
    Same shape as GET /api/overview when not in snapshot mode.
    If fetch_live_price is False, live_price stays None and price_warn empty (export-only).
    """
    from btc_paper.public_settings import public_settings_payload

    live_price: Optional[float] = None
    price_warn = ""
    if fetch_live_price:
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
        "settings": public_settings_payload(settings),
    }
