from __future__ import annotations

import logging
import signal
import sys
import time

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from btc_paper.pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("btc_paper.scheduler")


def job() -> None:
    try:
        summary = run_pipeline()
        log.info("pipeline ok: %s", summary)
    except Exception:
        log.exception("pipeline failed")


def main() -> None:
    scheduler = BlockingScheduler()
    scheduler.add_job(
        job,
        CronTrigger(hour=9, minute=0, timezone="Asia/Singapore"),
        id="daily_btc_pipeline",
        replace_existing=True,
    )

    def shutdown(signum, frame) -> None:  # type: ignore[no-untyped-def]
        log.info("shutdown signal %s", signum)
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    log.info("scheduler started; next run daily 09:00 Asia/Singapore")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
