from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd

from btc_paper.config import Settings
from btc_paper.ml.feature_schema import FEATURE_COLUMNS, FEATURE_VERSION


@dataclass
class HorizonPrediction:
    target: str
    prob_up: float
    predicted_class: int
    model_name: str


class MLSignalEngine:
    """Loads horizon models + metadata produced by `train_ml_models`."""

    def __init__(self, models_dir: str | Path) -> None:
        self.models_dir = Path(models_dir)
        metadata_path = self.models_dir / "model_metadata.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata file not found: {metadata_path}")
        self.metadata: Dict[str, Any] = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.horizon_targets = ["target_up_1h", "target_up_12h", "target_up_24h"]
        self.models = {
            target: joblib.load(self.models_dir / f"{target}_model.joblib")
            for target in self.horizon_targets
        }

    def _row_to_frame(self, feature_row: Dict[str, float] | pd.Series) -> pd.DataFrame:
        if isinstance(feature_row, pd.Series):
            data = feature_row.to_dict()
        else:
            data = dict(feature_row)
        frame = {}
        for col in FEATURE_COLUMNS:
            v = data.get(col, np.nan)
            try:
                frame[col] = [float(v)]
            except (TypeError, ValueError):
                frame[col] = [np.nan]
        return pd.DataFrame(frame)

    def predict(
        self,
        feature_row: Dict[str, float] | pd.Series,
        *,
        w_1h: float = 0.2,
        w_12h: float = 0.4,
        w_24h: float = 0.4,
    ) -> Dict[str, Any]:
        X = self._row_to_frame(feature_row)
        horizon_preds: Dict[str, HorizonPrediction] = {}

        for target in self.horizon_targets:
            model = self.models[target]
            prob_up = float(model.predict_proba(X)[:, 1][0])
            if not np.isfinite(prob_up):
                prob_up = 0.5
            prob_up = float(np.clip(prob_up, 0.0, 1.0))
            pred_class = int(prob_up >= 0.5)
            meta_h = self.metadata.get("horizons", {}).get(target, {})
            model_name = str(meta_h.get("best_model_name", "unknown"))
            horizon_preds[target] = HorizonPrediction(
                target=target,
                prob_up=prob_up,
                predicted_class=pred_class,
                model_name=model_name,
            )

        p1 = horizon_preds["target_up_1h"].prob_up
        p12 = horizon_preds["target_up_12h"].prob_up
        p24 = horizon_preds["target_up_24h"].prob_up
        ml_prob = w_1h * p1 + w_12h * p12 + w_24h * p24
        ml_prob = float(np.clip(ml_prob, 0.0, 1.0))
        ml_score = float(2.0 * (ml_prob - 0.5))

        if ml_score > 0.2:
            ml_bias = "bullish"
        elif ml_score < -0.2:
            ml_bias = "bearish"
        else:
            ml_bias = "neutral"

        trained_at = self.metadata.get("trained_at")
        return {
            "horizon_predictions": {
                key: {
                    "prob_up": value.prob_up,
                    "predicted_class": value.predicted_class,
                    "model_name": value.model_name,
                }
                for key, value in horizon_preds.items()
            },
            "ml_prob": ml_prob,
            "ml_score": ml_score,
            "ml_bias": ml_bias,
            "feature_version": self.metadata.get("feature_version", FEATURE_VERSION),
            "training_run_at": trained_at,
        }


def blend_final_score(
    news_score: float,
    technical_score: float,
    ml_score: float,
    *,
    w_news: float,
    w_tech: float,
    w_ml: float,
) -> float:
    return w_news * news_score + w_tech * technical_score + w_ml * ml_score


def decide_action(final_score: float, buy_threshold: float = 0.35, sell_threshold: float = -0.35) -> str:
    if final_score > buy_threshold:
        return "BUY"
    if final_score < sell_threshold:
        return "SELL"
    return "HOLD"


def try_ml_predict(settings: Settings, feature_row: Dict[str, float]) -> Optional[Dict[str, Any]]:
    """
    Run ML inference if enabled and artifacts exist; otherwise None.
    Never raises for missing models (pipeline stays up).
    """
    if not settings.ml_enabled:
        return None
    root = Path.cwd()
    models_dir = settings.models_dir if settings.models_dir.is_absolute() else root / settings.models_dir
    meta = models_dir / "model_metadata.json"
    if not meta.exists():
        return None
    try:
        engine = MLSignalEngine(models_dir)
        return engine.predict(
            feature_row,
            w_1h=settings.ml_horizon_weight_1h,
            w_12h=settings.ml_horizon_weight_12h,
            w_24h=settings.ml_horizon_weight_24h,
        )
    except Exception:  # noqa: BLE001
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run ML inference on one JSON feature row.")
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--json-row", required=True, help="JSON object with feature columns")
    args = parser.parse_args()

    engine = MLSignalEngine(models_dir=args.models_dir)
    row = json.loads(args.json_row)
    result = engine.predict(row)
    print(json.dumps(result, indent=2))
