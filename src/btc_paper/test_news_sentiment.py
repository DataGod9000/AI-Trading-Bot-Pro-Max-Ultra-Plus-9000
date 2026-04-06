"""
Smoke test: Yahoo BTC news scraper + FinBERT sentiment (no DB, no CoinGecko).

Run from project root (with venv activated):
  btc-paper-test-news

Or:
  PYTHONPATH=src python -m btc_paper.test_news_sentiment
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from btc_paper.config import load_settings
from btc_paper.scraper.yahoo_news import (
    articles_to_payload,
    fetch_yahoo_btc_news,
    fetch_yahoo_btc_news_debug,
)
from btc_paper.sentiment.finbert import (
    FINBERT_CHAR_LIMIT,
    FinBERTSentiment,
    aggregate_news_score,
    compose_article_text_for_finbert,
)


def main() -> None:
    settings = load_settings()
    print("=== 1) Scraper (Yahoo / yfinance, merged tickers) ===", flush=True)
    dbg = fetch_yahoo_btc_news_debug(settings)
    print(json.dumps(dbg, indent=2), flush=True)
    articles = fetch_yahoo_btc_news(settings)
    print(f"Articles after dedupe + 24h filter: {len(articles)}", flush=True)
    if not articles:
        print(
            "No articles returned. Check network, or Yahoo may have changed / rate-limited.",
            file=sys.stderr,
        )
        sys.exit(1)
    for i, a in enumerate(articles[:5], 1):
        print(f"\n--- #{i} ---", flush=True)
        print(f"title: {a.headline[:200]}", flush=True)
        print(f"url: {a.url}", flush=True)
        print(f"published: {a.published_at}", flush=True)

    payload = articles_to_payload(articles[:10])
    print("\n=== Raw payload sample (JSON) ===", flush=True)
    print(json.dumps(payload[:2], indent=2), flush=True)

    print("\n=== 2) Sentiment (FinBERT; first run downloads weights) ===", flush=True)
    engine = FinBERTSentiment(settings)
    now = datetime.now(timezone.utc)
    scores: list[float] = []
    for i, art in enumerate(articles[: min(5, len(articles))], 1):
        finbert_text = compose_article_text_for_finbert(art.headline, art.snippet)
        model_slice = finbert_text[:FINBERT_CHAR_LIMIT]
        s = engine.analyze_article(
            headline=art.headline,
            snippet=art.snippet,
            published_at=art.published_at,
            scraped_at=now,
        )
        scores.append(s.final_article_score)
        print(f"\n--- Article {i} ---", flush=True)
        print(
            f"  FinBERT input ({len(finbert_text)} chars; model sees {len(model_slice)}):",
            flush=True,
        )
        print(model_slice, flush=True)
        if len(finbert_text) > FINBERT_CHAR_LIMIT:
            print(
                f"  ... ({len(finbert_text) - FINBERT_CHAR_LIMIT} more chars omitted by [:FINBERT_CHAR_LIMIT])",
                flush=True,
            )
        print(f"  label:       {s.sentiment_label}", flush=True)
        print(f"  score:       {s.sentiment_score:+.4f}  (pos_prob - neg_prob)", flush=True)
        print(f"  confidence:  {s.confidence:.4f}", flush=True)
        print(f"  impact:      {s.impact} (weight {s.impact_weight})", flush=True)
        print(f"  recency w:   {s.recency_weight}", flush=True)
        print(f"  final score: {s.final_article_score:+.4f}", flush=True)

    agg = aggregate_news_score(scores)
    print("\n=== 3) Aggregate news_score (subset) ===", flush=True)
    print(f"news_score ≈ {agg:+.4f} (from {len(scores)} articles)", flush=True)
    print("\nDone.", flush=True)


if __name__ == "__main__":
    main()
