from __future__ import annotations

import json
import sys

from btc_paper.pipeline import run_pipeline


def run_once() -> None:
    summary = run_pipeline()
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    run_once()
