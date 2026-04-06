"""
Smoke test: CoinGecko BTC data + 1h/4h technical analysis (no DB, no news, no FinBERT).

Run from project root (venv activated):
  btc-paper-test-tech

Or:
  PYTHONPATH=src python -m btc_paper.test_technical
"""
from __future__ import annotations

import json
import sys
from typing import Optional

from btc_paper.config import load_settings
from btc_paper.technical.indicators import TimeframeAnalysis
from btc_paper.technical.live_analysis import compute_live_technical


def _print_timeframe(name: str, ta: Optional[TimeframeAnalysis], err: Optional[str]) -> None:
    print(f"\n=== {name} ===", flush=True)
    if err:
        print(f"  error: {err}", flush=True)
        return
    if ta is None:
        print("  (skipped — need at least 60 candles)", flush=True)
        return
    print(f"  score (normalized):     {ta.score:+.4f}", flush=True)
    print(f"  trend:                  {ta.trend}  (+1 bull stack, -1 bear stack, 0 mixed)", flush=True)
    print(f"  RSI(14):                {ta.rsi:.2f}", flush=True)
    print(f"  RSI contribution:       {ta.rsi_signal:+.2f}", flush=True)
    print(f"  Bollinger contribution: {ta.bollinger_signal:+.2f}", flush=True)
    print(f"  MACD contribution:      {ta.macd_signal:+.2f}", flush=True)
    print(f"  volatility_high:        {ta.volatility_high}", flush=True)
    print("  detail (JSON):", flush=True)
    print(json.dumps(ta.detail, indent=2, default=str), flush=True)


def main() -> None:
    settings = load_settings()
    rep = compute_live_technical(settings)

    print("=== 0) CoinGecko spot BTC/USD ===", flush=True)
    if rep.spot_error:
        print(f"  failed: {rep.spot_error}", file=sys.stderr, flush=True)
        sys.exit(1)
    print(f"  spot: ${rep.spot_usd:,.2f}", flush=True)

    print("\n=== 1) Fetch 1h series (market_chart, ~hourly) ===", flush=True)
    if rep.err_1h:
        print(f"  failed: {rep.err_1h}", flush=True)
    else:
        print(f"  candles: {rep.series_1h_candles}", flush=True)
        print(f"  range:   {rep.series_1h_start} → {rep.series_1h_end}", flush=True)

    print("\n=== 2) Fetch 4h series (OHLC, ~4h bars for 30d) ===", flush=True)
    if rep.err_4h:
        print(f"  failed: {rep.err_4h}", flush=True)
    else:
        print(f"  candles: {rep.series_4h_candles}", flush=True)
        print(f"  range:   {rep.series_4h_start} → {rep.series_4h_end}", flush=True)

    _print_timeframe("3) Analysis 1h", rep.ta_1h, rep.err_1h)
    _print_timeframe("4) Analysis 4h", rep.ta_4h, rep.err_4h)

    print("\n=== 5) Blended technical_score (same weights as pipeline) ===", flush=True)
    w1, w4 = rep.weight_1h, rep.weight_4h
    if rep.ta_1h and rep.ta_4h and rep.technical_score is not None:
        print(f"  weights: 1h={w1}, 4h={w4}", flush=True)
        print(
            f"  technical_score = {w1}*{rep.ta_1h.score:+.4f} + {w4}*{rep.ta_4h.score:+.4f} = {rep.technical_score:+.4f}",
            flush=True,
        )
    elif rep.ta_1h and rep.technical_score is not None:
        print(f"  4h missing — using 1h only: {rep.technical_score:+.4f}", flush=True)
    elif rep.ta_4h and rep.technical_score is not None:
        print(f"  1h missing — using 4h only: {rep.technical_score:+.4f}", flush=True)
    else:
        print("  no timeframe — would be 0.0 in pipeline", flush=True)
        sys.exit(1)

    print("\nDone.", flush=True)


if __name__ == "__main__":
    main()
