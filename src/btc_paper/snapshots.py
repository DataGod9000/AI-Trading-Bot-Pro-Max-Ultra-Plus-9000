"""Read precomputed demo files when SNAPSHOT_MODE is enabled."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from btc_paper.config import Settings
from btc_paper.public_settings import public_settings_payload


def snapshot_root(settings: Settings) -> Path:
    root = settings.snapshot_dir
    if not root.is_absolute():
        return Path.cwd() / root
    return root


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_metadata(settings: Settings) -> Dict[str, Any]:
    p = snapshot_root(settings) / "metadata.json"
    if not p.exists():
        return {}
    try:
        return dict(_read_json(p))
    except (OSError, json.JSONDecodeError):
        return {}


def demo_snapshot_flags(settings: Settings) -> Dict[str, Any]:
    if not settings.snapshot_mode:
        return {
            "enabled": False,
            "last_refreshed": None,
            "data_range": None,
            "source": None,
        }
    meta = load_metadata(settings)
    last = meta.get("last_updated") or meta.get("generated_at")
    return {
        "enabled": True,
        "last_refreshed": last,
        "data_range": meta.get("data_range"),
        "source": meta.get("source"),
    }


def load_overview_snapshot(settings: Settings) -> Dict[str, Any]:
    path = snapshot_root(settings) / "overview_snapshot.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing snapshot file: {path}")
    return dict(_read_json(path))


def load_latest_signal_snapshot(settings: Settings) -> Dict[str, Any]:
    path = snapshot_root(settings) / "latest_signal.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing snapshot file: {path}")
    return dict(_read_json(path))


def load_backtest_run_snapshot(settings: Settings) -> Dict[str, Any]:
    root = snapshot_root(settings)
    metrics_path = root / "backtest_metrics.json"
    equity_path = root / "backtest_equity.csv"
    if not metrics_path.exists():
        raise FileNotFoundError(f"Missing snapshot file: {metrics_path}")
    payload = dict(_read_json(metrics_path))
    if equity_path.exists():
        df = pd.read_csv(equity_path)
        ts_col = "ts" if "ts" in df.columns else "timestamp"
        if ts_col not in df.columns or "equity" not in df.columns:
            raise ValueError(f"{equity_path} must have columns: ts (or timestamp), equity")
        bench_col = "benchmark_equity" if "benchmark_equity" in df.columns else None
        payload["equity_curve"] = [
            {"ts": str(row[ts_col]), "equity": float(row["equity"])} for _, row in df.iterrows()
        ]
        if bench_col:
            payload["benchmark_curve"] = [
                {"ts": str(row[ts_col]), "equity": float(row[bench_col])} for _, row in df.iterrows()
            ]
    else:
        payload.setdefault("equity_curve", [])
    return payload


def _aggregate_trades_perf(closed: List[Dict[str, Any]]) -> Dict[str, Any]:
    pnls = [float(r["pnl"]) for r in closed if r.get("pnl") is not None and str(r.get("pnl")) != "nan"]
    wins = sum(1 for p in pnls if p > 0)
    return {
        "trade_count": len(pnls),
        "wins": wins,
        "avg_pnl": float(sum(pnls) / len(pnls)) if pnls else 0.0,
        "total_pnl": float(sum(pnls)),
        "min_pnl": float(min(pnls)) if pnls else 0.0,
        "max_pnl": float(max(pnls)) if pnls else 0.0,
    }


def load_trades_snapshot(settings: Settings, limit: int) -> Dict[str, Any]:
    path = snapshot_root(settings) / "trade_log.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing snapshot file: {path}")
    df = pd.read_csv(path)
    rows: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        row = {k: r[k] for k in df.columns}
        # Normalize for JSON (numpy types)
        for k, v in list(row.items()):
            if pd.isna(v):
                row[k] = None
            elif hasattr(v, "item"):
                row[k] = v.item()
        for k in ("id", "signal_id"):
            if row.get(k) is not None:
                try:
                    row[k] = int(float(row[k]))
                except (TypeError, ValueError):
                    pass
        # Canonical export columns (entry_time / exit_time / size) map to API shape
        if "entry_ts" not in row and row.get("entry_time") is not None:
            row["entry_ts"] = row["entry_time"]
        if "exit_ts" not in row and row.get("exit_time") is not None:
            row["exit_ts"] = row["exit_time"]
        if "qty" not in row and row.get("size") is not None:
            row["qty"] = row["size"]
        rows.append(row)

    open_trade = next((x for x in rows if str(x.get("status", "")).upper() == "OPEN"), None)
    closed_all = [x for x in rows if str(x.get("status", "")).upper() == "CLOSED"]
    closed_all.sort(key=lambda x: str(x.get("exit_ts") or ""), reverse=True)
    perf = _aggregate_trades_perf(closed_all)
    closed = closed_all[:limit]
    return {"closed": closed, "open_trade": open_trade, "performance": perf}


def load_signals_recent_snapshot(settings: Settings, n: int) -> Dict[str, Any]:
    path = snapshot_root(settings) / "signal_history.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing snapshot file: {path}")
    df = pd.read_csv(path)
    rows: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        d = {k: (None if pd.isna(r[k]) else r[k]) for k in df.columns}
        for k, v in list(d.items()):
            if hasattr(v, "item"):
                d[k] = v.item()
        if d.get("id") is not None:
            try:
                d["id"] = int(float(d["id"]))
            except (TypeError, ValueError):
                pass
        br = d.get("breakdown_json")
        if isinstance(br, str) and br.strip():
            try:
                d["breakdown"] = json.loads(br)
            except json.JSONDecodeError:
                d["breakdown"] = None
        elif "breakdown" not in d:
            d["breakdown"] = None
        rows.append(d)
    rows.sort(key=lambda x: str(x.get("run_at", x.get("timestamp", ""))), reverse=True)
    return {"signals": rows[:n]}


def load_backtest_compare_snapshot(settings: Settings) -> Dict[str, Any]:
    root = snapshot_root(settings)
    for name in ("strategy_compare.json", "backtest_compare.json"):
        path = root / name
        if path.exists():
            return dict(_read_json(path))
    raise FileNotFoundError(f"Missing snapshot file: {root / 'strategy_compare.json'}")


def load_backtest_walkforward_snapshot(settings: Settings) -> Dict[str, Any]:
    root = snapshot_root(settings)
    for name in ("walkforward_metrics.json", "backtest_walkforward.json"):
        path = root / name
        if path.exists():
            return dict(_read_json(path))
    raise FileNotFoundError(f"Missing snapshot file: {root / 'walkforward_metrics.json'}")


def _artifacts_model_info_path(settings: Settings) -> Path:
    root = Path.cwd()
    adir = settings.artifacts_dir if settings.artifacts_dir.is_absolute() else root / settings.artifacts_dir
    return adir / "metadata" / "model_info.json"


def _models_metadata_path(settings: Settings) -> Path:
    root = Path.cwd()
    mdir = settings.models_dir if settings.models_dir.is_absolute() else root / settings.models_dir
    return mdir / "model_metadata.json"


def load_ml_summary_snapshot(settings: Settings, hist_n: int) -> Dict[str, Any]:
    """Assemble /api/ml/summary from snapshot files (no torch / DB)."""
    root = snapshot_root(settings)
    latest_path = root / "latest_signal.json"
    ml_latest_path = root / "ml_latest.json"
    pred_path = root / "ml_predictions.csv"

    latest_sig: Optional[Dict[str, Any]] = None
    if latest_path.exists():
        latest_sig = dict(_read_json(latest_path)).get("signal")

    meta_path = _artifacts_model_info_path(settings)
    metadata: Optional[Dict[str, Any]] = None
    meta_path_str = str(meta_path)
    if meta_path.exists():
        try:
            metadata = dict(_read_json(meta_path))
        except (OSError, json.JSONDecodeError):
            metadata = None
    if metadata is None:
        fallback = _models_metadata_path(settings)
        meta_path_str = str(fallback)
        if fallback.exists():
            try:
                metadata = dict(_read_json(fallback))
            except (OSError, json.JSONDecodeError):
                metadata = None

    if ml_latest_path.exists():
        try:
            frozen_ml = dict(_read_json(ml_latest_path))
            if latest_sig is None:
                latest_sig = {
                    "run_at": frozen_ml.get("timestamp"),
                    "final_score": frozen_ml.get("confidence"),
                    "action": "HOLD",
                    "reason": "snapshot:ml_latest.json",
                    "breakdown": {
                        "ml": {
                            "ml_prob": frozen_ml.get("probability"),
                            "ml_bias": frozen_ml.get("prediction"),
                            "horizon_predictions": {},
                        }
                    },
                }
        except (OSError, json.JSONDecodeError):
            pass

    breakdown = (latest_sig or {}).get("breakdown") if isinstance(latest_sig, dict) else {}
    if not isinstance(breakdown, dict):
        breakdown = {}
    ml_block = breakdown.get("ml")
    weights = breakdown.get("weights")

    hist: List[Dict[str, Any]] = []
    if pred_path.exists():
        df = pd.read_csv(pred_path)
        df = df.tail(hist_n) if len(df) > hist_n else df
        for _, r in df.iterrows():
            ts = r["timestamp"] if "timestamp" in df.columns else r.get("run_at", "")
            hist.append(
                {
                    "run_at": str(ts) if not pd.isna(ts) else "",
                    "action": str(r["action"]) if "action" in df.columns and pd.notna(r.get("action")) else "",
                    "final_score": float(r["final_score"])
                    if "final_score" in df.columns and pd.notna(r.get("final_score"))
                    else 0.0,
                    "ml_score": float(r["ml_score"])
                    if "ml_score" in df.columns and pd.notna(r.get("ml_score"))
                    else 0.0,
                    "ml_prob": float(r["probability"])
                    if "probability" in df.columns and pd.notna(r.get("probability"))
                    else None,
                    "p_1h": float(r["prob_1h"])
                    if "prob_1h" in df.columns and pd.notna(r.get("prob_1h"))
                    else None,
                    "p_12h": float(r["prob_12h"])
                    if "prob_12h" in df.columns and pd.notna(r.get("prob_12h"))
                    else None,
                    "p_24h": float(r["prob_24h"])
                    if "prob_24h" in df.columns and pd.notna(r.get("prob_24h"))
                    else None,
                    "ml_bias": str(r["prediction"])
                    if "prediction" in df.columns and pd.notna(r.get("prediction"))
                    else None,
                }
            )
        hist.reverse()

    return {
        "metadata": metadata,
        "meta_path": meta_path_str,
        "latest_signal": latest_sig,
        "ml_block": ml_block,
        "weights": weights,
        "conflict_dampened": bool(breakdown.get("conflict_dampened")),
        "reason": (latest_sig or {}).get("reason") if latest_sig else None,
        "history": hist,
        "settings": public_settings_payload(settings),
        "snapshot": True,
    }


def load_history_snapshot(settings: Settings, ml_limit: int, sig_limit: int) -> Dict[str, Any]:
    root = snapshot_root(settings)
    ml_predictions: List[Dict[str, Any]] = []
    pred_path = root / "ml_predictions.csv"
    if pred_path.exists():
        df = pd.read_csv(pred_path).tail(ml_limit)
        for _, r in df.iterrows():
            row = {k: (None if pd.isna(r[k]) else r[k]) for k in df.columns}
            for k, v in list(row.items()):
                if hasattr(v, "item"):
                    row[k] = v.item()
            ml_predictions.append(row)
    sig_path = root / "signal_history.csv"
    signal_points: List[Dict[str, Any]] = []
    if sig_path.exists():
        df = pd.read_csv(sig_path).tail(sig_limit)
        for _, r in df.iterrows():
            ts = r.get("timestamp", r.get("run_at", ""))
            action = str(r.get("action", "")) if pd.notna(r.get("action", None)) else ""
            pos = r.get("position")
            if pd.isna(pos) or pos is None:
                au = action.upper()
                pos = "LONG" if au == "BUY" else "SHORT" if au == "SELL" else "FLAT"
            signal_points.append(
                {
                    "timestamp": str(ts),
                    "final_score": float(r["final_score"]) if pd.notna(r.get("final_score")) else 0.0,
                    "position": str(pos),
                    "action": action,
                }
            )
    return {"ml_predictions": ml_predictions, "signal_points": signal_points}


def load_market_analysis_snapshot(settings: Settings) -> Optional[Dict[str, Any]]:
    path = snapshot_root(settings) / "market_analysis.json"
    if not path.exists():
        return None
    return dict(_read_json(path))


def settings_public_snapshot(settings: Settings) -> Dict[str, Any]:
    """Merge frozen overview settings (if present) with live public_settings for any new keys."""
    root = snapshot_root(settings)
    overview_path = root / "overview_snapshot.json"
    base: Dict[str, Any]
    if overview_path.exists():
        ov = _read_json(overview_path)
        base = dict(ov.get("settings") or public_settings_payload(settings))
    else:
        base = public_settings_payload(settings)
    base = dict(base)
    meta = load_metadata(settings)
    base["demo_snapshot"] = {
        "enabled": True,
        "last_refreshed": meta.get("last_updated") or meta.get("generated_at"),
        "data_range": meta.get("data_range"),
        "source": meta.get("source"),
    }
    return base
