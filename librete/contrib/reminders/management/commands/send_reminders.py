import logging
import signal
import threading
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import close_old_connections, transaction
from django.utils import timezone

from librete.contrib.reminders.models import WorkerRun
from librete.contrib.reminders.sender import send_due_reminders
from librete.contrib.reminders.services import top_up_series_reminders

logger = logging.getLogger("librete.contrib.reminders")

TOP_UP = "series-reminders"
# The rolling window of series reminders is moved forward this often (at least daily).
TOP_UP_INTERVAL = timedelta(hours=12)


def top_up_if_due(now=None):
    """Run the series reminder top-up unless it ran within TOP_UP_INTERVAL.

    The last run is kept in the database (`WorkerRun`), so restarts don't repeat it and
    concurrent workers don't run it twice. Returns the number of series refreshed, or None.
    """
    now = now or timezone.now()
    with transaction.atomic():
        WorkerRun.objects.get_or_create(name=TOP_UP)
        run = WorkerRun.objects.select_for_update().get(name=TOP_UP)
        if run.last_run_at is not None and now - run.last_run_at < TOP_UP_INTERVAL:
            return None
        count = top_up_series_reminders(now)
        run.last_run_at = now
        run.save(update_fields=["last_run_at"])
    logger.info("Reminder window of %d recurring events topped up", count)
    return count


def run_once():
    """One pass of the worker: top up series reminders when due, send every due reminder."""
    top_up_if_due()
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
    help = (
        "Send due event and task reminders via Web Push and top up the reminders of "
        "recurring events (every 12 h). Use --loop to keep running (worker)."
    )

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
