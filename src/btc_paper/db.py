from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Generator, Iterable, List, Optional

from btc_paper.config import Settings


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS news_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    headline TEXT NOT NULL,
    snippet TEXT,
    source TEXT,
    url TEXT NOT NULL UNIQUE,
    published_at TEXT,
    scraped_at TEXT NOT NULL,
    sentiment_label TEXT,
    sentiment_score REAL,
    sentiment_confidence REAL,
    impact TEXT,
    final_article_score REAL
);

CREATE TABLE IF NOT EXISTS candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timeframe TEXT NOT NULL,
    ts INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL,
    UNIQUE(timeframe, ts)
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    btc_price REAL NOT NULL,
    news_score REAL NOT NULL,
    technical_score REAL NOT NULL,
    final_score REAL NOT NULL,
    action TEXT NOT NULL,
    confidence REAL NOT NULL,
    reason TEXT NOT NULL,
    breakdown_json TEXT
);

CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    side TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    qty REAL NOT NULL,
    entry_ts TEXT NOT NULL,
    exit_ts TEXT,
    status TEXT NOT NULL,
    pnl REAL,
    exit_reason TEXT,
    FOREIGN KEY(signal_id) REFERENCES signals(id)
);

-- Cached per-bar reconstructed signals for backtesting (idempotent upsert by timeframe+ts).
CREATE TABLE IF NOT EXISTS signal_bars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timeframe TEXT NOT NULL,
    ts INTEGER NOT NULL,
    news_score REAL NOT NULL,
    technical_score REAL NOT NULL,
    ml_score REAL NOT NULL,
    final_score REAL NOT NULL,
    source TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    UNIQUE(timeframe, ts)
);

CREATE INDEX IF NOT EXISTS idx_candles_tf_ts ON candles(timeframe, ts);
CREATE INDEX IF NOT EXISTS idx_signals_run_at ON signals(run_at);
CREATE INDEX IF NOT EXISTS idx_trades_status ON paper_trades(status);
CREATE INDEX IF NOT EXISTS idx_signal_bars_tf_ts ON signal_bars(timeframe, ts);
"""


def init_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def connect(settings: Settings) -> Generator[sqlite3.Connection, None, None]:
    init_db(settings.database_path)
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def insert_news_article(
    conn: sqlite3.Connection,
    *,
    headline: str,
    snippet: str,
    source: Optional[str],
    url: str,
    published_at: Optional[datetime],
    scraped_at: datetime,
    sentiment_label: Optional[str] = None,
    sentiment_score: Optional[float] = None,
    sentiment_confidence: Optional[float] = None,
    impact: Optional[str] = None,
    final_article_score: Optional[float] = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO news_articles (
            headline, snippet, source, url, published_at, scraped_at,
            sentiment_label, sentiment_score, sentiment_confidence, impact, final_article_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            headline=excluded.headline,
            snippet=excluded.snippet,
            source=excluded.source,
            published_at=excluded.published_at,
            scraped_at=excluded.scraped_at,
            sentiment_label=excluded.sentiment_label,
            sentiment_score=excluded.sentiment_score,
            sentiment_confidence=excluded.sentiment_confidence,
            impact=excluded.impact,
            final_article_score=excluded.final_article_score
        RETURNING id
        """,
        (
            headline,
            snippet,
            source,
            url,
            _iso(published_at),
            _iso(scraped_at),
            sentiment_label,
            sentiment_score,
            sentiment_confidence,
            impact,
            final_article_score,
        ),
    )
    row = cur.fetchone()
    conn.commit()
    return int(row[0])


def replace_candles(
    conn: sqlite3.Connection,
    timeframe: str,
    rows: Iterable[tuple[int, float, float, float, float, Optional[float]]],
) -> None:
    conn.execute("DELETE FROM candles WHERE timeframe = ?", (timeframe,))
    conn.executemany(
        """
        INSERT INTO candles (timeframe, ts, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [(timeframe, ts, o, h, l, c, v) for ts, o, h, l, c, v in rows],
    )
    conn.commit()


def upsert_candles(
    conn: sqlite3.Connection,
    timeframe: str,
    rows: Iterable[tuple[int, float, float, float, float, Optional[float]]],
) -> int:
    """
    Idempotent candle ingest: insert or update rows keyed by (timeframe, ts).
    Returns number of processed rows (not SQLite 'changes').
    """
    cur = conn.executemany(
        """
        INSERT INTO candles (timeframe, ts, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(timeframe, ts) DO UPDATE SET
            open=excluded.open,
            high=excluded.high,
            low=excluded.low,
            close=excluded.close,
            volume=excluded.volume
        """,
        [(timeframe, ts, o, h, l, c, v) for ts, o, h, l, c, v in rows],
    )
    conn.commit()
    return cur.rowcount if cur.rowcount is not None else 0


def upsert_signal_bars(
    conn: sqlite3.Connection,
    *,
    timeframe: str,
    rows: Iterable[tuple[int, float, float, float, float, str, str]],
) -> int:
    """
    Upsert reconstructed signal bars keyed by (timeframe, ts).
    Row tuple: (ts, news_score, technical_score, ml_score, final_score, source, computed_at_iso)
    """
    cur = conn.executemany(
        """
        INSERT INTO signal_bars (
            timeframe, ts, news_score, technical_score, ml_score, final_score, source, computed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(timeframe, ts) DO UPDATE SET
            news_score=excluded.news_score,
            technical_score=excluded.technical_score,
            ml_score=excluded.ml_score,
            final_score=excluded.final_score,
            source=excluded.source,
            computed_at=excluded.computed_at
        """,
        [(timeframe, ts, ns, tsig, ms, fs, src, ca) for ts, ns, tsig, ms, fs, src, ca in rows],
    )
    conn.commit()
    return cur.rowcount if cur.rowcount is not None else 0


def fetch_signal_bars_all(conn: sqlite3.Connection, *, timeframe: str) -> list[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT ts, news_score, technical_score, ml_score, final_score, source, computed_at
        FROM signal_bars
        WHERE timeframe = ?
        ORDER BY ts ASC
        """,
        (timeframe,),
    )
    return list(cur.fetchall())


def insert_signal(
    conn: sqlite3.Connection,
    *,
    run_at: datetime,
    btc_price: float,
    news_score: float,
    technical_score: float,
    final_score: float,
    action: str,
    confidence: float,
    reason: str,
    breakdown: Optional[dict[str, Any]] = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO signals (
            run_at, btc_price, news_score, technical_score, final_score,
            action, confidence, reason, breakdown_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            _iso(run_at),
            btc_price,
            news_score,
            technical_score,
            final_score,
            action,
            confidence,
            reason,
            json.dumps(breakdown) if breakdown is not None else None,
        ),
    )
    row = cur.fetchone()
    conn.commit()
    return int(row[0])


def insert_paper_trade(
    conn: sqlite3.Connection,
    *,
    signal_id: Optional[int],
    side: str,
    entry_price: float,
    qty: float,
    entry_ts: datetime,
    status: str = "OPEN",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO paper_trades (
            signal_id, side, entry_price, exit_price, qty, entry_ts, exit_ts, status, pnl, exit_reason
        ) VALUES (?, ?, ?, NULL, ?, ?, NULL, ?, NULL, NULL)
        RETURNING id
        """,
        (signal_id, side, entry_price, qty, _iso(entry_ts), status),
    )
    row = cur.fetchone()
    conn.commit()
    return int(row[0])


def close_paper_trade(
    conn: sqlite3.Connection,
    trade_id: int,
    *,
    exit_price: float,
    exit_ts: datetime,
    pnl: float,
    exit_reason: str,
) -> None:
    conn.execute(
        """
        UPDATE paper_trades
        SET exit_price = ?, exit_ts = ?, status = 'CLOSED', pnl = ?, exit_reason = ?
        WHERE id = ?
        """,
        (exit_price, _iso(exit_ts), pnl, exit_reason, trade_id),
    )
    conn.commit()


def get_open_paper_trade(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    cur = conn.execute(
        "SELECT * FROM paper_trades WHERE status = 'OPEN' ORDER BY id DESC LIMIT 1"
    )
    return cur.fetchone()


def fetch_recent_signals(conn: sqlite3.Connection, limit: int = 30) -> list[sqlite3.Row]:
    cur = conn.execute(
        "SELECT * FROM signals ORDER BY datetime(run_at) DESC LIMIT ?",
        (limit,),
    )
    return list(cur.fetchall())


def fetch_closed_trades(conn: sqlite3.Connection, limit: int = 200) -> list[sqlite3.Row]:
    cur = conn.execute(
        "SELECT * FROM paper_trades WHERE status = 'CLOSED' ORDER BY datetime(exit_ts) DESC LIMIT ?",
        (limit,),
    )
    return list(cur.fetchall())


def fetch_candles_all(conn: sqlite3.Connection, *, timeframe: str) -> list[sqlite3.Row]:
    """All OHLCV rows for a timeframe, oldest → newest."""
    cur = conn.execute(
        """
        SELECT ts, open, high, low, close, volume
        FROM candles
        WHERE timeframe = ?
        ORDER BY ts ASC
        """,
        (timeframe,),
    )
    return list(cur.fetchall())


def fetch_signals_chronological(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Signals ordered by run time (for joining news_score into historical feature rows)."""
    cur = conn.execute(
        """
        SELECT run_at, news_score, technical_score
        FROM signals
        ORDER BY datetime(run_at) ASC
        """
    )
    return list(cur.fetchall())


def fetch_candles_recent(
    conn: sqlite3.Connection, *, timeframe: str, max_bars: int = 400
) -> list[sqlite3.Row]:
    """Most recent `max_bars` rows for a timeframe, ordered oldest → newest (chart-friendly)."""
    cur = conn.execute(
        """
        SELECT ts, open, high, low, close, volume
        FROM (
            SELECT ts, open, high, low, close, volume
            FROM candles
            WHERE timeframe = ?
            ORDER BY ts DESC
            LIMIT ?
        )
        ORDER BY ts ASC
        """,
        (timeframe, max_bars),
    )
    return list(cur.fetchall())


def fetch_latest_signal(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    cur = conn.execute(
        "SELECT * FROM signals ORDER BY datetime(run_at) DESC LIMIT 1"
    )
    return cur.fetchone()


def fetch_recent_news(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT * FROM news_articles
        ORDER BY datetime(scraped_at) DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    )
    return list(cur.fetchall())


def _row_effective_utc(row: sqlite3.Row) -> Optional[datetime]:
    """Prefer published time; fall back to when we scraped."""
    for key in ("published_at", "scraped_at"):
        raw = row[key]
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return None


def fetch_news_last_hours(conn: sqlite3.Connection, hours: int = 24) -> List[sqlite3.Row]:
    """Articles whose published (or scrape) time falls within the last `hours` (UTC)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cur = conn.execute(
        """
        SELECT * FROM news_articles
        ORDER BY datetime(COALESCE(published_at, scraped_at)) DESC,
                 datetime(scraped_at) DESC,
                 id DESC
        """
    )
    out: List[sqlite3.Row] = []
    for row in cur.fetchall():
        eff = _row_effective_utc(row)
        if eff is None or eff < cutoff:
            continue
        out.append(row)
    return out


def fetch_news_for_run(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT * FROM news_articles
        ORDER BY datetime(scraped_at) DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    )
    return list(cur.fetchall())


def aggregate_news_sentiment_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    """Summary over all stored articles with FinBERT scores."""
    cur = conn.execute(
        """
        SELECT
            COUNT(*) AS n,
            AVG(CAST(sentiment_score AS REAL)) AS avg_sentiment,
            AVG(CAST(final_article_score AS REAL)) AS avg_final,
            AVG(CAST(sentiment_confidence AS REAL)) AS avg_confidence,
            SUM(CASE WHEN sentiment_label = 'bullish' THEN 1 ELSE 0 END) AS n_bull,
            SUM(CASE WHEN sentiment_label = 'bearish' THEN 1 ELSE 0 END) AS n_bear,
            SUM(CASE WHEN sentiment_label = 'neutral' THEN 1 ELSE 0 END) AS n_neu
        FROM news_articles
        WHERE final_article_score IS NOT NULL
        """
    )
    row = cur.fetchone()
    n = int(row["n"] or 0)
    return {
        "articles_scored": n,
        "avg_finbert_sentiment_score": float(row["avg_sentiment"] or 0) if n else None,
        "avg_weighted_article_score": float(row["avg_final"] or 0) if n else None,
        "avg_confidence": float(row["avg_confidence"] or 0) if n else None,
        "label_counts": {
            "bullish": int(row["n_bull"] or 0),
            "bearish": int(row["n_bear"] or 0),
            "neutral": int(row["n_neu"] or 0),
        },
    }


def fetch_news_daily_aggregates(conn: sqlite3.Connection, *, max_days: int = 90) -> List[dict[str, Any]]:
    """
    One row per calendar day (UTC date prefix of published_at or scraped_at).
    avg_final is the mean of impact × recency weighted scores; avg_sentiment is raw FinBERT pos−neg.
    """
    cur = conn.execute(
        """
        SELECT
            substr(COALESCE(NULLIF(trim(published_at), ''), scraped_at), 1, 10) AS day,
            AVG(CAST(sentiment_score AS REAL)) AS avg_sentiment,
            AVG(CAST(final_article_score AS REAL)) AS avg_final,
            COUNT(*) AS n
        FROM news_articles
        WHERE final_article_score IS NOT NULL
          AND scraped_at IS NOT NULL
        GROUP BY day
        HAVING length(day) = 10 AND substr(day, 5, 1) = '-' AND substr(day, 8, 1) = '-'
        ORDER BY day ASC
        """
    )
    out: List[dict[str, Any]] = [
        {
            "day": str(r["day"]),
            "avg_sentiment": float(r["avg_sentiment"] or 0),
            "avg_final": float(r["avg_final"] or 0),
            "count": int(r["n"] or 0),
        }
        for r in cur.fetchall()
    ]
    if max_days > 0 and len(out) > max_days:
        return out[-max_days:]
    return out


def aggregate_performance(conn: sqlite3.Connection) -> dict[str, Any]:
    cur = conn.execute(
        """
        SELECT
            COUNT(*) AS n,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
            AVG(pnl) AS avg_pnl,
            SUM(pnl) AS total_pnl,
            MIN(pnl) AS min_pnl,
            MAX(pnl) AS max_pnl
        FROM paper_trades
        WHERE status = 'CLOSED' AND pnl IS NOT NULL
        """
    )
    row = cur.fetchone()
    return {
        "trade_count": int(row["n"] or 0),
        "wins": int(row["wins"] or 0),
        "avg_pnl": float(row["avg_pnl"] or 0),
        "total_pnl": float(row["total_pnl"] or 0),
        "min_pnl": float(row["min_pnl"] or 0),
        "max_pnl": float(row["max_pnl"] or 0),
    }


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.replace(microsecond=0).isoformat()
