"""
Export local DB + backtests + ML history into data/snapshots/* for SNAPSHOT_MODE.

Run from repo root:

  btc-paper-export-snapshots
  python scripts/export_snapshots.py
  python -m btc_paper.snapshot_export --no-live-price
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd

from btc_paper import db
from btc_paper.api_server import _jsonable_signal_row, _row_to_dict
from btc_paper.backtest.dataset import generate_backtest_dataset
from btc_paper.backtest.engine import run_backtest
from btc_paper.backtest.schemas import BacktestParams
from btc_paper.config import load_settings
from btc_paper.overview_data import build_overview_payload
from btc_paper.snapshots import snapshot_root


def _write_json(path: Any, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def _score_curve_from_df(df: Any) -> List[Dict[str, Any]]:
    score_curve: List[Dict[str, Any]] = []
    if df is None or len(df) == 0 or "timestamp" not in df.columns or "final_score" not in df.columns:
        return score_curve
    for _ts, _s in zip(df["timestamp"].tolist(), df["final_score"].astype(float).tolist()):
        ts_str = _ts.isoformat() if hasattr(_ts, "isoformat") else str(_ts)
        score_curve.append({"ts": ts_str, "final_score": float(_s)})
    return score_curve


def _action_to_position(action: str) -> str:
    a = (action or "").upper()
    if a == "BUY":
        return "LONG"
    if a == "SELL":
        return "SHORT"
    return "FLAT"


def _num(v: Any) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        x = float(v)
        return x if pd.notna(x) else None
    except (TypeError, ValueError):
        return None


def _walkforward_payload(
    df: Any,
    *,
    train_bars: int,
    test_bars: int,
    step_bars: int,
    params_base: BacktestParams,
    initial_capital: float,
) -> Dict[str, Any]:
    windows: List[Dict[str, Any]] = []
    oos_parts: List[Dict[str, Any]] = []
    eq0 = float(initial_capital)
    i = 0
    while True:
        train_end = i + train_bars
        test_end = train_end + test_bars
        if test_end > len(df):
            break
        test_df = df.iloc[train_end:test_end].copy()
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
        "params": params_base.__dict__,
    }


def _export_ml_snapshots(root: Any, settings: Any) -> None:
    with db.connect(settings) as conn:
        cur = conn.execute("SELECT * FROM signals ORDER BY datetime(run_at) ASC")
        rows = list(cur.fetchall())

    pred_rows: List[Dict[str, Any]] = []
    for r in rows:
        rowd = _jsonable_signal_row(r)
        br = rowd.get("breakdown") or {}
        if not isinstance(br, dict):
            br = {}
        ml = br.get("ml") or {}
        hp = ml.get("horizon_predictions") or {}
        p1 = (hp.get("target_up_1h") or {}).get("prob_up")
        p12 = (hp.get("target_up_12h") or {}).get("prob_up")
        p24 = (hp.get("target_up_24h") or {}).get("prob_up")
        pred_rows.append(
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
    pd.DataFrame(pred_rows).to_csv(root / "ml_predictions.csv", index=False)

    latest: Dict[str, Any] = {}
    if rows:
        rowd = _jsonable_signal_row(rows[-1])
        br = rowd.get("breakdown") or {}
        ml = br.get("ml") or {} if isinstance(br, dict) else {}
        hp = ml.get("horizon_predictions") or {}

        def _hp_prob(key: str) -> float | None:
            block = hp.get(key) or {}
            return _num(block.get("prob_up")) if isinstance(block, dict) else None

        latest = {
            "timestamp": rowd.get("run_at"),
            "prediction": ml.get("ml_bias"),
            "confidence": abs(_num(rowd.get("final_score")) or 0.0),
            "probability": _num(ml.get("ml_prob")),
            "probabilities": {
                "1h": _hp_prob("target_up_1h"),
                "12h": _hp_prob("target_up_12h"),
                "24h": _hp_prob("target_up_24h"),
            },
            "source": "local_export",
        }
    _write_json(root / "ml_latest.json", latest)


def _trade_export_row(r: Dict[str, Any]) -> Dict[str, Any]:
    d = dict(r)
    out = {
        "entry_time": d.get("entry_ts"),
        "exit_time": d.get("exit_ts"),
        "side": d.get("side"),
        "pnl": d.get("pnl"),
        "size": d.get("qty"),
        **d,
    }
    return out


def run_export(*, fetch_live_price: bool = True) -> None:
    settings = load_settings()
    root = snapshot_root(settings)
    root.mkdir(parents=True, exist_ok=True)

    print(f"Exporting snapshots → {root}")

    ov = build_overview_payload(settings, fetch_live_price=fetch_live_price)
    _write_json(root / "overview_snapshot.json", ov)
    _write_json(root / "latest_signal.json", {"signal": ov.get("signal")})

    params = BacktestParams(
        sizing_mode=settings.backtest_sizing_mode,
        buy_threshold=settings.backtest_buy_threshold,
        sell_threshold=settings.backtest_sell_threshold,
        fee_bps=settings.backtest_fee_bps,
        slippage_bps=settings.backtest_slippage_bps,
        vol_window=settings.backtest_vol_window,
        max_position_size=settings.backtest_max_position_size,
        target_volatility=settings.backtest_target_volatility,
        initial_capital=settings.backtest_initial_capital,
    )
    ds = generate_backtest_dataset(settings)
    res = run_backtest(ds.df, params)
    score_curve = _score_curve_from_df(ds.df)
    metrics: Dict[str, Any] = {
        "summary": res.summary.__dict__,
        "drawdown_curve": res.drawdown_curve,
        "benchmark_curve": res.benchmark_curve,
        "exposure_curve": res.exposure_curve,
        "score_curve": score_curve,
        "trades": res.trades,
        "params": res.params,
        "dataset_source": ds.source,
        "bars": len(ds.df),
    }
    _write_json(root / "backtest_metrics.json", metrics)

    eq = res.equity_curve
    bc = res.benchmark_curve
    if eq and bc and len(eq) == len(bc):
        pd.DataFrame(
            {
                "ts": [str(x["ts"]) for x in eq],
                "equity": [float(x["equity"]) for x in eq],
                "benchmark_equity": [float(x["equity"]) for x in bc],
            }
        ).to_csv(root / "backtest_equity.csv", index=False)
    else:
        pd.DataFrame(res.equity_curve).to_csv(root / "backtest_equity.csv", index=False)

    with db.connect(settings) as conn:
        cur = conn.execute("SELECT * FROM paper_trades ORDER BY id ASC")
        trade_rows = [dict(r) for r in cur.fetchall()]
    if trade_rows:
        pd.DataFrame([_trade_export_row(r) for r in trade_rows]).to_csv(root / "trade_log.csv", index=False)
    else:
        pd.DataFrame(
            columns=[
                "entry_time",
                "exit_time",
                "side",
                "pnl",
                "size",
                "id",
                "signal_id",
                "entry_ts",
                "exit_ts",
                "qty",
                "status",
                "exit_reason",
            ]
        ).to_csv(root / "trade_log.csv", index=False)

    with db.connect(settings) as conn:
        cur = conn.execute("SELECT * FROM signals ORDER BY id ASC")
        sig_rows = [dict(r) for r in cur.fetchall()]
    if sig_rows:
        enriched = []
        for r in sig_rows:
            d = dict(r)
            d["timestamp"] = d.get("run_at")
            d["position"] = _action_to_position(str(d.get("action", "")))
            enriched.append(d)
        pd.DataFrame(enriched).to_csv(root / "signal_history.csv", index=False)
    else:
        pd.DataFrame(
            columns=[
                "id",
                "timestamp",
                "run_at",
                "position",
                "btc_price",
                "news_score",
                "technical_score",
                "final_score",
                "action",
                "confidence",
                "reason",
                "breakdown_json",
            ]
        ).to_csv(root / "signal_history.csv", index=False)

    modes = ["fixed", "confidence", "confidence_vol"]
    results: List[Dict[str, Any]] = []
    curves: Dict[str, Any] = {}
    for m in modes:
        p = BacktestParams(**{**params.__dict__, "sizing_mode": m})
        r = run_backtest(ds.df, p)
        results.append({"sizing_mode": m, **r.summary.__dict__})
        curves[m] = r.equity_curve
    compare_payload = {
        "metrics": results,
        "equity_curves": curves,
        "benchmark_curve": run_backtest(
            ds.df, BacktestParams(initial_capital=settings.backtest_initial_capital)
        ).benchmark_curve,
        "bars": len(ds.df),
        "dataset_source": ds.source,
    }
    _write_json(root / "strategy_compare.json", compare_payload)
    _write_json(root / "backtest_compare.json", compare_payload)

    df = ds.df
    if df is not None and len(df) > 0:
        wf_params = BacktestParams(
            sizing_mode="fixed",
            buy_threshold=0.35,
            sell_threshold=-0.35,
            fee_bps=settings.backtest_fee_bps,
            slippage_bps=settings.backtest_slippage_bps,
            vol_window=settings.backtest_vol_window,
            max_position_size=settings.backtest_max_position_size,
            target_volatility=settings.backtest_target_volatility,
            initial_capital=settings.backtest_initial_capital,
        )
        wf = _walkforward_payload(
            df,
            train_bars=24 * 30,
            test_bars=24 * 7,
            step_bars=24 * 7,
            params_base=wf_params,
            initial_capital=settings.backtest_initial_capital,
        )
        wf["dataset_source"] = ds.source
        _write_json(root / "walkforward_metrics.json", wf)
        _write_json(root / "backtest_walkforward.json", wf)
    else:
        empty_wf = {
            "summary": None,
            "equity_curve": [],
            "windows": [],
            "bars": 0,
            "dataset_source": ds.source,
            "params": {},
        }
        _write_json(root / "walkforward_metrics.json", empty_wf)
        _write_json(root / "backtest_walkforward.json", empty_wf)

    with db.connect(settings) as conn:
        sig_rows_m = db.fetch_recent_signals(conn, 120)
        news_rows = db.fetch_recent_news(conn, 400)
        c_1h = db.fetch_candles_recent(conn, timeframe="1h", max_bars=200)
        c_4h = db.fetch_candles_recent(conn, timeframe="4h", max_bars=200)
    signals = [_jsonable_signal_row(r) for r in reversed(sig_rows_m)]
    market_payload = {
        "signals": signals,
        "candles_1h": [_row_to_dict(r) for r in c_1h],
        "candles_4h": [_row_to_dict(r) for r in c_4h],
        "news": [_row_to_dict(r) for r in news_rows],
    }
    _write_json(root / "market_analysis.json", market_payload)

    _export_ml_snapshots(root, settings)

    data_range = "unknown"
    if df is not None and len(df) and "timestamp" in df.columns:
        t0 = pd.Timestamp(df["timestamp"].min())
        t1 = pd.Timestamp(df["timestamp"].max())
        data_range = f"{t0.date()}..{t1.date()}"

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    meta = {
        "snapshot_mode": True,
        "last_updated": now,
        "data_range": data_range,
        "source": "local_export",
        "generated_at": now,
        "snapshot_version": 2,
    }
    _write_json(root / "metadata.json", meta)
    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export snapshot files for SNAPSHOT_MODE deployment.")
    parser.add_argument(
        "--no-live-price",
        action="store_true",
        help="Do not call CoinGecko when building overview_snapshot (fully offline export).",
    )
    args = parser.parse_args()
    run_export(fetch_live_price=not args.no_live_price)


if __name__ == "__main__":
    main()
