import logging
import signal
import threading

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from librete.contrib.reminders.sender import send_due_reminders

logger = logging.getLogger("librete.contrib.reminders")


def run_once():
    """One pass of the worker: send every due reminder."""
    result = send_due_reminders()
    if result:
        logger.info(
            "Reminders: %d sent, %d skipped (too late); pushes: %d delivered, %d failed, "
            "%d expired subscriptions removed",
            result.reminders,
            result.skipped,
            result.delivered,
            result.failed,
            result.removed,
        )
    return result


def run_forever(interval, stop):
    """Run `run_once` every `interval` seconds until `stop` (a threading.Event) is set."""
    while not stop.is_set():
        # A long-running process must drop connections that are broken or too old.
        close_old_connections()
        try:
            run_once()
        except Exception:
            # e.g. the database is restarting; try again on the next tick.
            logger.exception("Sending reminders failed")
        stop.wait(interval)


class Command(BaseCommand):
    help = "Send due event reminders via Web Push. Use --loop to keep running (worker)."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Run until stopped.")
        parser.add_argument(
            "--interval", type=int, default=60, help="Seconds between runs with --loop."
        )

    def handle(self, *args, loop=False, interval=60, **options):
        if not loop:
            run_once()
            return
        stop = threading.Event()
        # The worker runs as PID 1 in Docker, which ignores SIGTERM without a handler.
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_: stop.set())
        logger.info("Reminder worker started (every %d s)", interval)
        run_forever(interval, stop)
        logger.info("Reminder worker stopped")
