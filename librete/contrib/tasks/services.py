"""Repeating tasks: the next instance created when a repeating task is completed."""

import uuid

from librete.utils import recurrence

from .models import Task


def due_date(task):
    """The date reminders and repeats are measured from: `end_date`, else `start_date`."""
    return task.end_date or task.start_date


def next_instance_client_id(task, next_due):
    """UUIDv5(NAMESPACE_URL, "librete:task-repeat:<series_key>:<next due, UTC>").

    `series_key` is the completed task's `client_id`, or `id:<pk>` without one. The app
    derives the same id when it completes a task offline, so the instance is never doubled.
    """
    series_key = str(task.client_id) if task.client_id else f"id:{task.pk}"
    name = f"librete:task-repeat:{series_key}:{recurrence.format_utc(next_due)}"
    return uuid.uuid5(uuid.NAMESPACE_URL, name)


def next_due_date(task):
    """The next occurrence strictly after the task's due date, or None (no rule, or ended)."""
    due = due_date(task)
    if not task.repeat or due is None:
        return None
    return recurrence.next_after(task.repeat, due, recurrence.zone(task.author.time_zone))


def remaining_rule(rule):
    """The rule for the next instance: COUNT counts the instances left, so it drops by one.

    Each instance expands the rule from its own due date, so without this a COUNT would
    never run out.
    """
    parts = rule.split(";")
    for index, part in enumerate(parts):
        name, _, value = part.partition("=")
        if name == "COUNT":
            parts[index] = f"COUNT={int(value) - 1}"
    return ";".join(parts)


def create_next_instance(task, using=None):
    """Create the instance after `task` (just completed); return it, or None.

    Nothing is created when the rule has ended or the instance already exists (the app
    created it offline with the same derived `client_id`).
    """
    next_due = next_due_date(task)
    if next_due is None:
        return None
    client_id = next_instance_client_id(task, next_due)
    manager = Task.objects.db_manager(using)
    if manager.filter(author_id=task.author_id, client_id=client_id).exists():
        return None
    delta = next_due - due_date(task)
    fields = {
        "name": task.name,
        "category_id": task.category_id,
        "parent_id": task.parent_id,
        "description": task.description,
        "priority": task.priority,
        "repeat": remaining_rule(task.repeat),
    }
    if hasattr(task, "reminders"):
        fields["reminders"] = list(task.reminders)
    return manager.create(
        author_id=task.author_id,
        client_id=client_id,
        status=Task.Status.ACTIVE,
        start_date=task.start_date + delta if task.start_date else None,
        end_date=task.end_date + delta if task.end_date else None,
        **fields,
    )
