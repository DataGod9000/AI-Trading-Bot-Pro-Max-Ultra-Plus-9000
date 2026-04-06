from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, List, Optional
from uuid import uuid4

import yfinance as yf

from btc_paper.config import Settings

# Yahoo often throttles or empties `BTC-USD` news; merge several BTC/crypto-adjacent tickers.
FALLBACK_TICKERS = ("BTC-USD", "IBIT", "COIN", "MSTR")


@dataclass
class RawArticle:
    headline: str
    snippet: str
    source: Optional[str]
    url: str
    published_at: Optional[datetime]


def _parse_publish_time(item: dict[str, Any]) -> Optional[datetime]:
    ts = (
        item.get("providerPublishTime")
        or item.get("pubDate")
        or item.get("displayTime")
        or item.get("publishTime")
    )
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        sec = int(ts)
        # Some payloads use milliseconds.
        if sec > 10_000_000_000:
            sec //= 1000
        return datetime.fromtimestamp(sec, tz=timezone.utc)
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _title_from_item(item: dict[str, Any]) -> str:
    for key in ("title", "headline", "name"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _link_from_item(item: dict[str, Any]) -> str:
    for key in ("link", "canonicalUrl", "url", "clickThroughUrl"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    for key in ("uuid", "id"):
        uid = item.get(key)
        if isinstance(uid, str) and uid.strip():
            return f"https://finance.yahoo.com/news/{uid.strip()}"
    return ""


def _snippet_from_item(item: dict[str, Any]) -> str:
    for key in ("summary", "description", "snippet"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _canonical_url_to_str(val: Any) -> str:
    if isinstance(val, str) and val.strip():
        return val.strip()
    if isinstance(val, dict):
        for k in ("url", "href", "canonicalUrl"):
            u = val.get(k)
            if isinstance(u, str) and u.strip():
                return u.strip()
    return ""


def _provider_source(content: dict[str, Any]) -> Optional[str]:
    prov = content.get("provider")
    if isinstance(prov, dict):
        return (prov.get("displayName") or prov.get("name") or prov.get("sourceName"))
    if isinstance(prov, str):
        return prov
    return None


def _parse_stream_article(item: dict[str, Any]) -> Optional[tuple[str, str, str, Optional[datetime], Optional[str]]]:
    """
    yfinance >= 0.2.50 returns Yahoo NCP stream items shaped like:
      {"id": "...", "content": {"title", "canonicalUrl"|..., "pubDate"|..., "summary"|...}}
    Older payloads had title/link at the top level.
    """
    content = item.get("content")
    if isinstance(content, dict):
        title = (content.get("title") or "").strip()
        link = _canonical_url_to_str(content.get("canonicalUrl") or content.get("clickThroughUrl"))
        if not link and item.get("id") is not None:
            sid = str(item["id"]).strip()
            if sid:
                link = f"https://finance.yahoo.com/news/{sid}"
        snippet = _snippet_from_item(content)
        published = _parse_publish_time(content) or _parse_publish_time(item)
        source = _provider_source(content) or (
            item.get("publisher") if isinstance(item.get("publisher"), str) else None
        )
        if title and link:
            return (title, link, snippet or title, published, source)
        return None

    title = _title_from_item(item)
    link = _link_from_item(item)
    if not title or not link:
        return None
    snippet = _snippet_from_item(item)
    published = _parse_publish_time(item)
    publisher = item.get("publisher")
    source = publisher if isinstance(publisher, str) else None
    return (title, link, snippet or title, published, source)


def _raw_news_for_ticker(symbol: str) -> List[dict[str, Any]]:
    t = yf.Ticker(symbol)
    news = t.news
    return list(news) if isinstance(news, list) else []


def fetch_yahoo_btc_news(settings: Settings) -> List[RawArticle]:
    """
    Merge Yahoo Finance news from several tickers (BTC-USD alone often returns []).
    Dedupes by URL. Keeps items with title + link; drops items older than lookback when
    Yahoo provides a publish timestamp (items with no timestamp are kept).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.news_lookback_hours)
    seen_urls: set[str] = set()
    out: List[RawArticle] = []

    for symbol in FALLBACK_TICKERS:
        items = _raw_news_for_ticker(symbol)
        for item in items:
            if not isinstance(item, dict):
                continue
            parsed = _parse_stream_article(item)
            if not parsed:
                continue
            title, link, snippet, published, source = parsed
            if link in seen_urls:
                continue
            if published is not None and published < cutoff:
                continue
            seen_urls.add(link)
            out.append(
                RawArticle(
                    headline=title,
                    snippet=snippet,
                    source=source,
                    url=link,
                    published_at=published,
                )
            )
    return out


def fetch_yahoo_btc_news_debug(settings: Settings) -> dict[str, Any]:
    """Counts at each stage — use for troubleshooting empty scrapes."""
    per_ticker: dict[str, Any] = {}
    for symbol in FALLBACK_TICKERS:
        items = _raw_news_for_ticker(symbol)
        sample: dict[str, Any] = {"raw_count": len(items), "sample_keys": []}
        if items and isinstance(items[0], dict):
            sample["sample_keys"] = sorted(items[0].keys())
            first = items[0]
            inner = first.get("content")
            if isinstance(inner, dict):
                sample["content_keys"] = sorted(inner.keys())[:20]
        per_ticker[symbol] = sample
    filtered = fetch_yahoo_btc_news(settings)
    return {"per_ticker": per_ticker, "after_filters": len(filtered)}


def dump_raw_news(settings: Settings, payload: Iterable[dict[str, Any]]) -> Path:
    settings.raw_news_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = settings.raw_news_dir / f"{stamp}_{uuid4().hex[:8]}.json"
    path.write_text(json.dumps(list(payload), indent=2), encoding="utf-8")
    return path


def articles_to_payload(articles: List[RawArticle]) -> List[dict[str, Any]]:
    return [
        {
            "headline": a.headline,
            "snippet": a.snippet,
            "source": a.source,
            "url": a.url,
            "published_at": a.published_at.isoformat() if a.published_at else None,
        }
        for a in articles
    ]
