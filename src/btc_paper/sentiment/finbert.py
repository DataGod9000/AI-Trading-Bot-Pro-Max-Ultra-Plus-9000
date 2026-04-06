from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from btc_paper.config import Settings

FINBERT_CHAR_LIMIT = 2000


def compose_article_text_for_finbert(headline: str, snippet: str) -> str:
    """Headline + snippet as one string; tokenizer truncates to FINBERT_CHAR_LIMIT."""
    return f"{headline}. {snippet}".strip()


HIGH_IMPACT = re.compile(
    r"\b(etf|sec|hack|exploit|breach|lawsuit|ban|approval|reject)\b",
    re.IGNORECASE,
)
MEDIUM_IMPACT = re.compile(
    r"\b(macro|adoption|inflation|rates|fed|institution|treasury|halving|mining)\b",
    re.IGNORECASE,
)


@dataclass
class ArticleSentiment:
    sentiment_label: str
    sentiment_score: float
    confidence: float
    impact: str
    impact_weight: float
    recency_weight: float
    final_article_score: float


def _impact_tier(text: str) -> Tuple[str, float]:
    if HIGH_IMPACT.search(text):
        return "high", 1.5
    if MEDIUM_IMPACT.search(text):
        return "medium", 1.2
    return "low", 1.0


def _recency_weight(now: datetime, published: Optional[datetime]) -> float:
    if published is None:
        return 1.0
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    delta_h = (now - published).total_seconds() / 3600.0
    delta_h = max(0.0, delta_h)
    if delta_h <= 2:
        return 1.5
    if delta_h <= 6:
        return 1.2
    return 1.0


def _label_from_finbert(pos: float, neg: float, neu: float) -> str:
    if pos > neg and pos > neu:
        return "bullish"
    if neg > pos and neg > neu:
        return "bearish"
    return "neutral"


class FinBERTSentiment:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tokenizer = AutoTokenizer.from_pretrained(settings.finbert_model)
        self._model = AutoModelForSequenceClassification.from_pretrained(settings.finbert_model)
        self._model.eval()

    @torch.inference_mode()
    def score_text(self, text: str) -> Tuple[float, float, Dict[str, float]]:
        enc = self._tokenizer(
            text[:FINBERT_CHAR_LIMIT],
            return_tensors="pt",
            truncation=True,
            padding=True,
        )
        logits = self._model(**enc).logits[0]
        probs = torch.softmax(logits, dim=-1).tolist()
        id2label = self._model.config.id2label
        label_probs = {id2label[i].lower(): float(probs[i]) for i in range(len(probs))}

        pos = float(label_probs.get("positive", 0.0))
        neg = float(label_probs.get("negative", 0.0))
        neu = float(label_probs.get("neutral", 0.0))
        sentiment_score = pos - neg
        confidence = max(pos, neg, neu)
        return sentiment_score, confidence, label_probs

    def analyze_article(
        self,
        *,
        headline: str,
        snippet: str,
        published_at: Optional[datetime],
        scraped_at: datetime,
    ) -> ArticleSentiment:
        text = compose_article_text_for_finbert(headline, snippet)
        sentiment_score, confidence, label_probs = self.score_text(text)
        impact, impact_w = _impact_tier(text)
        now = scraped_at if scraped_at.tzinfo else scraped_at.replace(tzinfo=timezone.utc)
        rec_w = _recency_weight(now, published_at)
        final = sentiment_score * impact_w * rec_w
        pos = float(label_probs.get("positive", 0.0))
        neg = float(label_probs.get("negative", 0.0))
        neu = float(label_probs.get("neutral", 0.0))
        label = _label_from_finbert(pos, neg, neu)
        return ArticleSentiment(
            sentiment_label=label,
            sentiment_score=float(sentiment_score),
            confidence=float(confidence),
            impact=impact,
            impact_weight=impact_w,
            recency_weight=rec_w,
            final_article_score=float(final),
        )


def aggregate_news_score(scores: List[float]) -> float:
    if not scores:
        return 0.0
    raw_mean = float(np.mean(scores))
    envelope = 1.5 * 1.5
    scaled = raw_mean / envelope
    return float(max(-1.0, min(1.0, scaled)))
