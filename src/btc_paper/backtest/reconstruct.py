from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from btc_paper.sentiment.finbert import aggregate_news_score
from btc_paper.technical.indicators import analyze_timeframe


def _parse_dt(raw: object) -> Optional[datetime]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def reconstruct_news_score_series(
    *,
    bars_ts: pd.Series,
    articles: pd.DataFrame,
    lookback_hours: int,
) -> pd.Series:
    """
    Retroactively compute news_score for each bar using only articles available up to that bar.

    Uses stored `final_article_score` (impact × recency weighted) from news_articles and applies
    the same aggregation function as production: `aggregate_news_score(scores)`.
    """
    if articles is None or len(articles) == 0:
        return pd.Series(0.0, index=bars_ts.index, name="news_score")

    lb = int(max(1, lookback_hours))
    art = articles.copy()
    art["effective_dt"] = art.apply(
        lambda r: _parse_dt(r.get("published_at")) or _parse_dt(r.get("scraped_at")),
        axis=1,
    )
    art = art.dropna(subset=["effective_dt", "final_article_score"])
    if art.empty:
        return pd.Series(0.0, index=bars_ts.index, name="news_score")

    art = art.sort_values("effective_dt")
    times = art["effective_dt"].tolist()
    scores = art["final_article_score"].astype(float).tolist()

    out: List[float] = []
    i = 0
    j = 0
    window_scores: List[float] = []

    for t in pd.to_datetime(bars_ts, utc=True).dt.to_pydatetime().tolist():
        tt = t.astimezone(timezone.utc)
        cutoff = tt - timedelta(hours=lb)

        while i < len(times) and times[i] < cutoff:
            # remove from window (keep multiset by naive list remove; ok for small counts)
            # for larger datasets we can optimize later.
            try:
                window_scores.remove(float(scores[i]))
            except ValueError:
                pass
            i += 1

        while j < len(times) and times[j] <= tt:
            window_scores.append(float(scores[j]))
            j += 1

        out.append(float(aggregate_news_score(window_scores)))

    return pd.Series(out, index=bars_ts.index, name="news_score")


def reconstruct_technical_score_series(
    *,
    ohlcv: pd.DataFrame,
) -> Tuple[pd.Series, pd.Series]:
    """
    Retroactively compute technical_score for each bar without lookahead.

    We rely on the indicator implementation's causal rolling/ewm behavior:
    analyzing the prefix df up to each bar is lookahead-safe.

    Returns:
    - technical_score series
    - rsi14 series (for optional UX/debug)
    """
    if ohlcv is None or len(ohlcv) == 0:
        z = pd.Series([], dtype="float64")
        return z, z

    # For portfolio-quality correctness, compute on expanding prefixes.
    # This is O(n^2) but acceptable for typical 30–180 day windows; optimize later if needed.
    scores: List[float] = []
    rsis: List[float] = []
    for k in range(1, len(ohlcv) + 1):
        sub = ohlcv.iloc[:k]
        if len(sub) < 60:
            scores.append(0.0)
            rsis.append(np.nan)
            continue
        ta = analyze_timeframe(sub, "1h")
        scores.append(float(ta.score))
        rsis.append(float(ta.rsi))

    return (
        pd.Series(scores, index=ohlcv.index, name="technical_score"),
        pd.Series(rsis, index=ohlcv.index, name="rsi14"),
    )

