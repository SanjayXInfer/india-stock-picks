"""APScheduler jobs (IST). Scraping runs on this schedule, never on page load."""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import IST
from .pipeline import run_scrape

log = logging.getLogger(__name__)

# (description, cron fields). Mirrors .github/workflows/publish.yml (which is in UTC).
SCHEDULE = [
    ("pre-market every 15 min, 07:00-09:15", dict(day_of_week="mon-fri", hour="7-8", minute="0,15,30,45")),
    ("pre-market 09:00/09:15", dict(day_of_week="mon-fri", hour="9", minute="0,15")),
    ("market hours hourly", dict(day_of_week="mon-fri", hour="10-15", minute="15")),
    ("evening every 30 min, 16:00-21:00", dict(hour="16-20", minute="0,30")),
    ("evening 21:00", dict(hour="21", minute="0")),
]


def start_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone=IST, job_defaults={"coalesce": True, "max_instances": 1,
                                                            "misfire_grace_time": 600})
    for i, (desc, fields) in enumerate(SCHEDULE):
        sched.add_job(run_scrape, CronTrigger(timezone=IST, **fields), id=f"scrape-{i}", name=desc)
    sched.start()
    log.info("scheduler started: %s", [j.name for j in sched.get_jobs()])
    return sched
