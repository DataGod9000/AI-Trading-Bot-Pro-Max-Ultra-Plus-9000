from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from btc_paper import db
from btc_paper.config import Settings
from btc_paper.scraper.yahoo_news import articles_to_payload, dump_raw_news, fetch_yahoo_btc_news
from btc_paper.sentiment.finbert import FinBERTSentiment


@dataclass(frozen=True)
class NewsIngestResult:
    raw_article_count: int
    scored_and_stored: int
    article_scores: List[float]
    top_headlines: List[str]


def sync_yahoo_news_to_db(
    settings: Settings,
    *,
    max_articles: int = 40,
    top_headlines_n: int = 3,
    scraped_at: Optional[datetime] = None,
    sentiment_engine: Optional[FinBERTSentiment] = None,
) -> NewsIngestResult:
    """
    Fetch Yahoo BTC-adjacent news, run FinBERT, upsert into news_articles.
    Used by the full pipeline and by the API / UI news sync action.
    """
    now = scraped_at if scraped_at is not None else datetime.now(timezone.utc)
    articles = fetch_yahoo_btc_news(settings)
    dump_raw_news(settings, articles_to_payload(articles))
    engine = sentiment_engine or FinBERTSentiment(settings)
    article_scores: List[float] = []
    top_headlines: List[str] = []
    n = 0
    with db.connect(settings) as conn:
        for art in articles[:max_articles]:
            s = engine.analyze_article(
                headline=art.headline,
                snippet=art.snippet,
                published_at=art.published_at,
                scraped_at=now,
            )
            article_scores.append(s.final_article_score)
            if len(top_headlines) < top_headlines_n:
                top_headlines.append(art.headline)
            db.insert_news_article(
                conn,
                headline=art.headline,
                snippet=art.snippet,
                source=art.source,
                url=art.url,
                published_at=art.published_at,
                scraped_at=now,
                sentiment_label=s.sentiment_label,
                sentiment_score=s.sentiment_score,
                sentiment_confidence=s.confidence,
                impact=s.impact,
                final_article_score=s.final_article_score,
            )
            n += 1
    return NewsIngestResult(
        raw_article_count=len(articles),
        scored_and_stored=n,
        article_scores=article_scores,
        top_headlines=top_headlines,
    )
