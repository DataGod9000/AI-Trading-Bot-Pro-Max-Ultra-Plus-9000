from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from btc_paper.config import Settings


@dataclass
class SignalResult:
    final_score: float
    action: str
    confidence: float
    reason: str
    breakdown: Dict[str, Any]


def _strong_disagreement(news_score: float, technical_score: float, ml_score: float, edge: float) -> bool:
    """PRD §6.7: dampen when bullish and bearish camps both have strong views."""
    scores = [news_score, technical_score, ml_score]
    pos = sum(1 for s in scores if s > edge)
    neg = sum(1 for s in scores if s < -edge)
    return pos >= 1 and neg >= 1


def _build_rationale(
    *,
    news_score: float,
    technical_score: float,
    ml_score: float,
    ml_bias: str,
    ml_active: bool,
    ml_prob: Optional[float],
    final_score: float,
    action: str,
    conflict_dampened: bool,
    news_summary: str,
    technical_summary: str,
) -> str:
    parts: list[str] = []

    def _tone(label: str, v: float) -> str:
        if v > 0.15:
            return f"{label} supportive ({v:+.2f})"
        if v < -0.15:
            return f"{label} cautious ({v:+.2f})"
        return f"{label} roughly neutral ({v:+.2f})"

    parts.append(_tone("Sentiment", news_score))
    parts.append(_tone("Technicals", technical_score))
    if ml_active and ml_prob is not None:
        parts.append(
            f"ML bias **{ml_bias}** (blended up-prob {ml_prob:.2f}, score {ml_score:+.2f} on −1…+1)."
        )
    else:
        parts.append("ML inactive or models missing — decision uses sentiment + technicals only.")

    parts.append(f"Unified score **{final_score:+.3f}** → **{action}**.")
    if conflict_dampened:
        parts.append("Strong cross-signal disagreement detected; score dampened ×0.7 per policy.")
    parts.append(f"Context — News: {news_summary} | Technicals: {technical_summary}")
    return " ".join(parts)


def combine_scores(
    settings: Settings,
    *,
    news_score: float,
    technical_score: float,
    news_summary: str,
    technical_summary: str,
    ml_score: float = 0.0,
    ml_active: bool = False,
    ml_payload: Optional[Dict[str, Any]] = None,
) -> SignalResult:
    """
    Unified signal (PRD §6): blend sentiment, technicals, and optional ML.
    When `ml_active` is False, weights are renormalized onto news + technical only.
    """
    if ml_active:
        wn = float(settings.news_weight)
        wt = float(settings.technical_weight)
        wm = float(settings.ml_weight)
        denom = wn + wt + wm
        if denom <= 0:
            final = 0.0
        else:
            final = (wn * news_score + wt * technical_score + wm * ml_score) / denom
    else:
        wn = float(settings.legacy_news_weight)
        wt = float(settings.legacy_technical_weight)
        s2 = wn + wt
        if s2 <= 0:
            final = 0.0
        else:
            final = (wn * news_score + wt * technical_score) / s2

    conflict = False
    if ml_active and _strong_disagreement(
        news_score,
        technical_score,
        ml_score,
        settings.signal_disagreement_edge,
    ):
        final *= settings.signal_conflict_dampen
        conflict = True

    if final > settings.signal_buy_threshold:
        action = "BUY"
    elif final < settings.signal_sell_threshold:
        action = "SELL"
    else:
        action = "HOLD"

    confidence = float(min(1.0, max(0.0, abs(final))))

    ml_bias = "neutral"
    ml_prob: Optional[float] = None
    if ml_payload:
        ml_bias = str(ml_payload.get("ml_bias", "neutral"))
        ml_prob = float(ml_payload["ml_prob"]) if ml_payload.get("ml_prob") is not None else None

    reason = _build_rationale(
        news_score=news_score,
        technical_score=technical_score,
        ml_score=ml_score,
        ml_bias=ml_bias,
        ml_active=ml_active,
        ml_prob=ml_prob,
        final_score=final,
        action=action,
        conflict_dampened=conflict,
        news_summary=news_summary,
        technical_summary=technical_summary,
    )

    breakdown: Dict[str, Any] = {
        "news_score": news_score,
        "technical_score": technical_score,
        "weights": {
            "news": float(settings.news_weight),
            "technical": float(settings.technical_weight),
            "ml": float(settings.ml_weight),
            "legacy_news": float(settings.legacy_news_weight),
            "legacy_technical": float(settings.legacy_technical_weight),
            "ml_active": ml_active,
        },
        "ml_score": ml_score if ml_active else 0.0,
        "conflict_dampened": conflict,
    }
    if ml_payload is not None:
        breakdown["ml"] = ml_payload

    return SignalResult(
        final_score=float(final),
        action=action,
        confidence=confidence,
        reason=reason,
        breakdown=breakdown,
    )
