from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from btc_paper.ml.feature_schema import FEATURE_COLUMNS, FEATURE_VERSION

try:
    from xgboost import XGBClassifier

    HAS_XGB = True
except ImportError:
    HAS_XGB = False


@dataclass
class HorizonConfig:
    name: str
    steps_ahead: int
    min_return: float


HORIZONS: List[HorizonConfig] = [
    HorizonConfig(name="target_up_1h", steps_ahead=1, min_return=0.0),
    HorizonConfig(name="target_up_12h", steps_ahead=12, min_return=0.005),
    HorizonConfig(name="target_up_24h", steps_ahead=24, min_return=0.01),
]


def load_dataset(csv_path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    if "timestamp" not in df.columns:
        raise ValueError("Dataset must contain a 'timestamp' column.")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.sort_values("timestamp").reset_index(drop=True)
    required_cols = set(FEATURE_COLUMNS + ["timestamp", "price_close"])
    missing = required_cols.difference(df.columns)
    if missing:
        raise ValueError(f"Dataset is missing required columns: {sorted(missing)}")
    return df


def add_targets(df: pd.DataFrame, horizons: List[HorizonConfig]) -> pd.DataFrame:
    out = df.copy()
    for horizon in horizons:
        future_close = out["price_close"].shift(-horizon.steps_ahead)
        future_return = (future_close - out["price_close"]) / out["price_close"]
        out[horizon.name] = (future_return > horizon.min_return).astype("Int64")
    return out


def chronological_split(df: pd.DataFrame, train_ratio: float = 0.8) -> Tuple[pd.DataFrame, pd.DataFrame]:
    split_idx = int(len(df) * train_ratio)
    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()
    return train_df, test_df


def build_candidate_models() -> Dict[str, Pipeline]:
    out: Dict[str, Pipeline] = {
        "logistic_regression": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("model", LogisticRegression(max_iter=3000, class_weight="balanced", solver="lbfgs")),
            ]
        ),
        "random_forest": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    RandomForestClassifier(
                        n_estimators=300,
                        max_depth=8,
                        min_samples_leaf=10,
                        random_state=42,
                        class_weight="balanced_subsample",
                    ),
                ),
            ]
        ),
    }
    if HAS_XGB:
        out["xgboost"] = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    XGBClassifier(
                        n_estimators=250,
                        max_depth=5,
                        learning_rate=0.05,
                        subsample=0.85,
                        colsample_bytree=0.85,
                        random_state=42,
                        eval_metric="logloss",
                    ),
                ),
            ]
        )
    else:
        out["hist_gradient_boosting"] = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    HistGradientBoostingClassifier(
                        max_depth=6,
                        learning_rate=0.05,
                        max_iter=300,
                        random_state=42,
                    ),
                ),
            ]
        )
    return out


def evaluate_model(model: Pipeline, X_test: pd.DataFrame, y_test: pd.Series) -> Dict[str, float]:
    prob_up = model.predict_proba(X_test)[:, 1]
    pred = (prob_up >= 0.5).astype(int)
    try:
        roc = float(roc_auc_score(y_test, prob_up))
    except ValueError:
        roc = float("nan")
    metrics = {
        "roc_auc": roc,
        "accuracy": float(accuracy_score(y_test, pred)),
        "precision": float(precision_score(y_test, pred, zero_division=0)),
        "recall": float(recall_score(y_test, pred, zero_division=0)),
        "f1": float(f1_score(y_test, pred, zero_division=0)),
        "positive_rate_predicted": float(pred.mean()),
        "positive_rate_actual": float(y_test.mean()),
    }
    return metrics


def train_one_horizon(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    target_col: str,
    models_dir: Path,
) -> Dict[str, Any]:
    feature_cols = FEATURE_COLUMNS.copy()
    train_local = train_df.dropna(subset=[target_col]).copy()
    test_local = test_df.dropna(subset=[target_col]).copy()

    X_train = train_local[feature_cols]
    y_train = train_local[target_col].astype(int)
    X_test = test_local[feature_cols]
    y_test = test_local[target_col].astype(int)

    candidates = build_candidate_models()
    results: Dict[str, Dict[str, float]] = {}
    fitted_models: Dict[str, Pipeline] = {}

    for model_name, model in candidates.items():
        model.fit(X_train, y_train)
        fitted_models[model_name] = model
        results[model_name] = evaluate_model(model, X_test, y_test)

    best_name = max(results, key=lambda k: results[k]["roc_auc"] if np.isfinite(results[k]["roc_auc"]) else -1.0)
    best_model = fitted_models[best_name]
    artifact_path = models_dir / f"{target_col}_model.joblib"
    joblib.dump(best_model, artifact_path)

    prob_up = best_model.predict_proba(X_test)[:, 1]
    pred = (prob_up >= 0.5).astype(int)
    report = classification_report(y_test, pred, zero_division=0, output_dict=True)

    return {
        "target": target_col,
        "best_model_name": best_name,
        "artifact_path": str(artifact_path),
        "feature_columns": feature_cols,
        "metrics_by_model": results,
        "classification_report": report,
        "test_rows": int(len(test_local)),
        "trained_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def train_all_models(
    csv_path: str | Path,
    output_dir: str | Path = "models",
    train_ratio: float = 0.8,
) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = load_dataset(csv_path)
    df = add_targets(df, HORIZONS)
    train_df, test_df = chronological_split(df, train_ratio=train_ratio)

    summary: Dict[str, Any] = {
        "dataset_path": str(csv_path),
        "row_count": int(len(df)),
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "horizons": {},
        "feature_version": FEATURE_VERSION,
        "feature_columns": FEATURE_COLUMNS.copy(),
        "trained_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "has_xgboost": HAS_XGB,
    }

    for horizon in HORIZONS:
        horizon_result = train_one_horizon(train_df, test_df, horizon.name, output_dir)
        summary["horizons"][horizon.name] = horizon_result

    metadata_path = output_dir / "model_metadata.json"
    metadata_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Train per-horizon ML models for BTC signals.")
    parser.add_argument("--csv", required=True, help="Path to ml_features.csv")
    parser.add_argument("--output-dir", default="models", help="Directory for joblib + metadata")
    parser.add_argument("--train-ratio", type=float, default=0.8)
    args = parser.parse_args()

    result = train_all_models(csv_path=args.csv, output_dir=args.output_dir, train_ratio=args.train_ratio)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
