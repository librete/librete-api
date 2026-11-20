"""Record every create, update and delete of a synced model in the change log.

Deletes cascade (category → its events, notes and tasks; task → subtasks) and Django sends
`post_delete` for every cascaded object, so each gets its own delete row. Queryset
`.update()` and `bulk_create()` bypass these signals: don't use them on synced models.
"""

from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from django.db.models.signals import post_delete, post_save, pre_delete

from librete.utils.models import lock_owner

from .models import Change
from .resources import TYPE_BY_MODEL
from .services import record_change


def _deleting_owner(origin):
    """Deleting a user deletes their objects and change log; nothing to record then."""
    user_model = get_user_model()
    if isinstance(origin, QuerySet):
        return issubclass(origin.model, user_model)
    return isinstance(origin, user_model)


def lock_before_delete(sender, instance, using, origin=None, **kwargs):
    # Collector.delete sends every pre_delete before deleting rows, so the owner lock is
    # taken before any row lock (the same order as saves, which avoids deadlocks).
    if not _deleting_owner(origin):
        lock_owner(instance.author_id, using)


def record_upsert(sender, instance, raw=False, **kwargs):
    if not raw:
        record_change(instance.author_id, TYPE_BY_MODEL[sender], instance.pk, Change.Op.UPSERT)


def record_delete(sender, instance, origin=None, **kwargs):
    if not _deleting_owner(origin):
        record_change(instance.author_id, TYPE_BY_MODEL[sender], instance.pk, Change.Op.DELETE)


for model in TYPE_BY_MODEL:
    uid = f"sync-{model._meta.label_lower}"
    pre_delete.connect(lock_before_delete, sender=model, dispatch_uid=uid)
    post_save.connect(record_upsert, sender=model, dispatch_uid=uid)
    post_delete.connect(record_delete, sender=model, dispatch_uid=uid)
