from __future__ import annotations

import random
import threading
import time
from typing import Any, Dict, List, Tuple

import httpx

from btc_paper.config import Settings

# CoinGecko OHLC granularity: 1-2 days -> ~30m; 3-30 days -> ~4h

_lock = threading.Lock()
# key -> (monotonic_expiry, parsed_json)
_response_cache: Dict[tuple[str, tuple[tuple[str, str], ...]], tuple[float, Any]] = {}


def _cache_key(path: str, params: Dict[str, str]) -> tuple[str, tuple[tuple[str, str], ...]]:
    return (path, tuple(sorted(params.items())))


def _cache_get(settings: Settings, key: tuple[str, tuple[tuple[str, str], ...]]) -> Any | None:
    ttl = int(settings.coingecko_cache_ttl_seconds)
    if ttl <= 0 or not settings.coingecko_cache_enabled:
        return None
    now = time.monotonic()
    with _lock:
        ent = _response_cache.get(key)
        if ent is None:
            return None
        exp, val = ent
        if now > exp:
            del _response_cache[key]
            return None
        return val


def _cache_set(settings: Settings, key: tuple[str, tuple[tuple[str, str], ...]], value: Any) -> None:
    ttl = int(settings.coingecko_cache_ttl_seconds)
    if ttl <= 0 or not settings.coingecko_cache_enabled:
        return
    now = time.monotonic()
    with _lock:
        if len(_response_cache) > 48:
            _response_cache.clear()
        _response_cache[key] = (now + float(ttl), value)


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """CoinGecko usually sends numeric Retry-After (seconds)."""
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def _request_coingecko_json(settings: Settings, path: str, params: Dict[str, str]) -> Any:
    """
    GET JSON with response caching (reduces 429s on repeated calls) and backoff on 429.

    CoinGecko's free tier is strict: burst traffic triggers limits. Cache TTL defaults
    to 120s; raise COINGECKO_CACHE_TTL if you need fresher prices and accept more 429 risk.
    """
    key = _cache_key(path, params)
    cached = _cache_get(settings, key)
    if cached is not None:
        return cached

    base = settings.coingecko_base_url.rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    last: httpx.Response | None = None
    max_retries = max(1, int(settings.coingecko_max_retries))

    for attempt in range(max_retries):
        with httpx.Client(timeout=35.0) as client:
            r = client.get(url, params=params)
            last = r
            if r.status_code == 429:
                ra = _retry_after_seconds(r) or 0.0
                base_wait = min(60.0, (2.0**attempt) + random.random())
                wait_s = max(base_wait, ra, 1.0)
                if attempt < max_retries - 1:
                    time.sleep(wait_s)
                    continue
            r.raise_for_status()
            data = r.json()
            _cache_set(settings, key, data)
            return data

    if last is not None:
        last.raise_for_status()
    raise httpx.HTTPError("CoinGecko request failed")


def fetch_ohlc(settings: Settings, *, days: int) -> List[List[float]]:
    data = _request_coingecko_json(
        settings,
        "coins/bitcoin/ohlc",
        {"vs_currency": "usd", "days": str(days)},
    )
    if not isinstance(data, list):
        raise ValueError("Unexpected OHLC payload")
    return data


def fetch_market_chart_hourly(settings: Settings, *, days: int = 30) -> List[Tuple[int, float]]:
    """
    CoinGecko returns ~hourly points for 2 < days <= 90 (per CoinGecko behavior for BTC).
    We treat each point as a synthetic OHLC candle (open=high=low=close=price).
    """
    data = _request_coingecko_json(
        settings,
        "coins/bitcoin/market_chart",
        {"vs_currency": "usd", "days": str(days)},
    )
    prices = data.get("prices") or []
    out: List[Tuple[int, float]] = []
    for pair in prices:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        ts_ms, px = pair[0], pair[1]
        out.append((int(ts_ms // 1000), float(px)))
    out.sort(key=lambda x: x[0])
    return out


def fetch_spot_price_usd(settings: Settings) -> float:
    data = _request_coingecko_json(
        settings,
        "simple/price",
        {"ids": "bitcoin", "vs_currencies": "usd"},
    )
    return float(data["bitcoin"]["usd"])


def ohlc_to_rows(
    ohlc: List[List[float]],
) -> List[Tuple[int, float, float, float, float, float]]:
    rows: List[Tuple[int, float, float, float, float, float]] = []
    for candle in ohlc:
        if len(candle) < 5:
            continue
        ts, o, h, l, c = candle[:5]
        rows.append((int(ts // 1000), float(o), float(h), float(l), float(c), 0.0))
    rows.sort(key=lambda x: x[0])
    return rows
