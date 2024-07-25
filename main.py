import os

import click
from apscheduler.schedulers.background import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from gmail_digest import cli


def handle_click_exit(func):
    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except click.exceptions.Exit as e:
            if e.exit_code != 0:
                raise

    return wrapper


def job():
    for command in list(cli.commands.values()):
        handle_click_exit(command)()


def cron():
    schedule = os.environ.get("SCHEDULE", "0 6 * * *")
    print(f"Running on schedule: {schedule}")

    scheduler = BlockingScheduler()
    scheduler.add_job(job, CronTrigger.from_crontab(schedule))
    scheduler.start()


if __name__ == "__main__":
    cron()
