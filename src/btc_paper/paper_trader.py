from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional, Tuple

import sqlite3

from btc_paper.config import Settings
from btc_paper import db


Side = Literal["BUY", "SELL"]


@dataclass
class ExitCheck:
    should_exit: bool
    reason: Optional[str] = None


def _parse_ts(row_val: Optional[str]) -> datetime:
    if not row_val:
        return datetime.now(timezone.utc)
    dt = datetime.fromisoformat(row_val)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def check_exit(
    settings: Settings,
    *,
    side: str,
    entry_price: float,
    current_price: float,
    entry_ts: datetime,
    now: datetime,
) -> ExitCheck:
    if side == "BUY":
        pnl_pct = (current_price - entry_price) / entry_price * 100.0
    else:
        pnl_pct = (entry_price - current_price) / entry_price * 100.0

    if pnl_pct >= settings.take_profit_pct:
        return ExitCheck(True, "take_profit")
    if pnl_pct <= -settings.stop_loss_pct:
        return ExitCheck(True, "stop_loss")
    hours = (now - entry_ts).total_seconds() / 3600.0
    if hours >= settings.max_hold_hours:
        return ExitCheck(True, "time_exit")
    return ExitCheck(False)


def realized_pnl(side: str, entry: float, exit_px: float, qty: float) -> float:
    if side == "BUY":
        return (exit_px - entry) * qty
    return (entry - exit_px) * qty


def position_qty(settings: Settings, price: float) -> float:
    return settings.paper_trade_usd / price


def _qty_for_usd(settings: Settings, price: float, usd_notional: Optional[float]) -> float:
    usd = float(usd_notional) if usd_notional is not None and usd_notional > 0 else float(settings.paper_trade_usd)
    return usd / price


def try_rule_based_exit(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    price: float,
    now: datetime,
) -> Tuple[bool, str]:
    """
    If an open position hits take-profit, stop-loss, or max hold, close at `price`.
    Same rules as the automated pipeline (`check_exit`).
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    open_row = db.get_open_paper_trade(conn)
    if open_row is None:
        return (False, "No open position.")
    side = str(open_row["side"])
    entry = float(open_row["entry_price"])
    qty = float(open_row["qty"])
    entry_ts = _parse_ts(open_row["entry_ts"])
    eid = int(open_row["id"])
    decision = check_exit(
        settings,
        side=side,
        entry_price=entry,
        current_price=price,
        entry_ts=entry_ts,
        now=now,
    )
    if not decision.should_exit:
        return (
            False,
            f"No rule hit yet (TP +{settings.take_profit_pct}%, SL −{settings.stop_loss_pct}%, "
            f"max hold {settings.max_hold_hours}h).",
        )
    pnl = realized_pnl(side, entry, price, qty)
    db.close_paper_trade(
        conn,
        eid,
        exit_price=price,
        exit_ts=now,
        pnl=pnl,
        exit_reason=decision.reason or "rule_exit",
    )
    return (True, f"Closed — {decision.reason}")


def manual_order(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    intent: Literal["buy", "sell", "close"],
    price: float,
    now: datetime,
    usd_notional: Optional[float] = None,
) -> Tuple[bool, str]:
    """
    Manual paper orders at `price` (market-style). Uses `signal_id=NULL`.
    - close: flatten only
    - buy/sell: open or flip (close opposite first)
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if price <= 0:
        return (False, "Invalid price.")

    if intent == "close":
        open_row = db.get_open_paper_trade(conn)
        if open_row is None:
            return (False, "No open position to close.")
        side = str(open_row["side"])
        entry = float(open_row["entry_price"])
        qty = float(open_row["qty"])
        eid = int(open_row["id"])
        pnl = realized_pnl(side, entry, price, qty)
        db.close_paper_trade(
            conn,
            eid,
            exit_price=price,
            exit_ts=now,
            pnl=pnl,
            exit_reason="manual_close",
        )
        return (True, f"Closed {side} at {price:,.2f} (PnL ${pnl:,.2f}).")

    desired: Side = "BUY" if intent == "buy" else "SELL"
    qty = _qty_for_usd(settings, price, usd_notional)

    open_row = db.get_open_paper_trade(conn)
    if open_row is not None:
        side = str(open_row["side"])
        if side == desired:
            return (False, f"Already in a {desired} position. Close or flip from the other side.")
        eid = int(open_row["id"])
        entry = float(open_row["entry_price"])
        oqty = float(open_row["qty"])
        pnl = realized_pnl(side, entry, price, oqty)
        db.close_paper_trade(
            conn,
            eid,
            exit_price=price,
            exit_ts=now,
            pnl=pnl,
            exit_reason="manual_flip",
        )

    tid = db.insert_paper_trade(
        conn,
        signal_id=None,
        side=desired,
        entry_price=price,
        qty=qty,
        entry_ts=now,
        status="OPEN",
    )
    return (True, f"Opened {desired} #{tid} @ {price:,.2f}, qty {qty:.8f} BTC (~${qty * price:,.2f}).")


def apply_signal(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    signal_id: int,
    action: str,
    price: float,
    now: datetime,
) -> Tuple[Optional[int], Optional[str]]:
    """
    Manage open position exits and new entries. Returns (trade_id, note).
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    open_row = db.get_open_paper_trade(conn)
    if open_row is not None:
        eid = int(open_row["id"])
        side = str(open_row["side"])
        entry = float(open_row["entry_price"])
        qty = float(open_row["qty"])
        entry_ts = _parse_ts(open_row["entry_ts"])
        exit_decision = check_exit(settings, side=side, entry_price=entry, current_price=price, entry_ts=entry_ts, now=now)
        if exit_decision.should_exit:
            pnl = realized_pnl(side, entry, price, qty)
            db.close_paper_trade(
                conn,
                eid,
                exit_price=price,
                exit_ts=now,
                pnl=pnl,
                exit_reason=exit_decision.reason or "exit",
            )
            open_row = None

    if open_row is None:
        open_row = db.get_open_paper_trade(conn)

    if action == "HOLD":
        return (int(open_row["id"]) if open_row is not None else None, "hold_no_new")

    desired: Side = "BUY" if action == "BUY" else "SELL"

    if open_row is not None:
        side = str(open_row["side"])
        if side == desired:
            return (int(open_row["id"]), "already_open_same_side")
        eid = int(open_row["id"])
        entry = float(open_row["entry_price"])
        qty = float(open_row["qty"])
        entry_ts = _parse_ts(open_row["entry_ts"])
        pnl = realized_pnl(side, entry, price, qty)
        db.close_paper_trade(
            conn,
            eid,
            exit_price=price,
            exit_ts=now,
            pnl=pnl,
            exit_reason="signal_reverse",
        )

    qty = position_qty(settings, price)
    tid = db.insert_paper_trade(
        conn,
        signal_id=signal_id,
        side=desired,
        entry_price=price,
        qty=qty,
        entry_ts=now,
        status="OPEN",
    )
    return (tid, "opened")
