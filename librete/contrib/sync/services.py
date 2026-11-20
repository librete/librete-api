from .models import Change


def record_change(user_id, type, object_id, op):
    """Make (type, object_id) the user's latest change: drop its old row, add a new one.

    Must run inside the transaction that changes the object, after `lock_owner`, so ids are
    committed in order (see `librete.utils.models.lock_owner`).
    """
    Change.objects.filter(user_id=user_id, type=type, object_id=object_id).delete()
    Change.objects.create(user_id=user_id, type=type, object_id=object_id, op=op)
