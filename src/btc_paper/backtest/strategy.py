from __future__ import annotations

import numpy as np
import pandas as pd


def score_to_direction(
    final_score: pd.Series, *, buy_threshold: float, sell_threshold: float
) -> pd.Series:
    """
    Convert unified signal score into a discrete direction:
      score > buy_threshold  -> +1 (long)
      score < sell_threshold -> -1 (short)
      else                  ->  0 (flat)
    """
    s = final_score.astype(float).fillna(0.0)
    out = np.where(s > float(buy_threshold), 1.0, np.where(s < float(sell_threshold), -1.0, 0.0))
    return pd.Series(out, index=final_score.index, name="direction")

