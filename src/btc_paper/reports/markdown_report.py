from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

from btc_paper.config import Settings


def write_daily_report(
    settings: Settings,
    *,
    run_at: datetime,
    btc_price: float,
    headlines: Sequence[str],
    news_score: float,
    technical_score: float,
    ml_score: float | None = None,
    final_score: float,
    action: str,
    confidence: float,
    reason: str,
    technical_notes: str,
    trade_note: str,
) -> Path:
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = run_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
    path = settings.reports_dir / f"{stamp}_report.md"
    lines: List[str] = [
        f"# BTC AI Paper Trading Report — {stamp}",
        "",
        f"- **Run (UTC)**: {run_at.astimezone(timezone.utc).isoformat()}",
        f"- **BTC price (USD)**: {btc_price:,.2f}",
        "",
        "## Final decision",
        "",
        f"- **Action**: {action}",
        f"- **Confidence**: {confidence:.2f}",
        f"- **Final score**: {final_score:+.3f} (news {news_score:+.3f}, technical {technical_score:+.3f}"
        + (
            f", ML {ml_score:+.3f})"
            if ml_score is not None
            else ")"
        ),
        f"- **Rationale**: {reason}",
        "",
        "## News snapshot",
        "",
    ]
    if headlines:
        for h in headlines:
            lines.append(f"- {h}")
    else:
        lines.append("- _(no headlines in the last window)_")
    lines.extend(
        [
            "",
            "## Technical summary",
            "",
            technical_notes,
            "",
            "## Paper trade",
            "",
            trade_note,
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
