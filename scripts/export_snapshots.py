#!/usr/bin/env python3
"""
Research → deployment: export SQLite + backtests + ML snapshots to data/snapshots/.

Run from repository root (adds src/ on sys.path for a bare `python scripts/export_snapshots.py`):

  python scripts/export_snapshots.py
  python scripts/export_snapshots.py --no-live-price

Installed package:

  btc-paper-export-snapshots
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
os.chdir(_ROOT)

from btc_paper.snapshot_export import main

if __name__ == "__main__":
    main()
