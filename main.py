import os

from apscheduler.schedulers.background import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from gmail_digest import main
from gmail_digest.internet import wait_for_internet_connection


def handle_click_exit(func):
    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except SystemExit as e:
            if e.code != 0:
                raise

    return wrapper


def job():
    wait_for_internet_connection()

    handle_click_exit(main)()


def cron():
    schedule = os.environ.get("SCHEDULE", "0 6 * * *")
    print(f"Running on schedule: {schedule}")

    scheduler = BlockingScheduler()
    scheduler.add_job(job, CronTrigger.from_crontab(schedule))
    scheduler.start()


if __name__ == "__main__":
    cron()
