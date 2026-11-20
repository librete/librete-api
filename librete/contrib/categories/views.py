from django.db.models import Count, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce

from librete.contrib.events.models import Event
from librete.contrib.notes.models import Note
from librete.contrib.tasks.models import Task
from librete.utils.viewsets import OwnedModelViewSet

from .models import Category
from .serializers import CategorySerializer


def _count(model):
    subquery = (
        model.objects.filter(category=OuterRef("pk"))
        .order_by()
        .values("category")
        .annotate(count=Count("pk"))
        .values("count")
    )
    return Coalesce(Subquery(subquery, output_field=IntegerField()), 0)


def with_counts(queryset):
    """Annotate categories with the `*_count` fields `CategorySerializer` returns."""
    return queryset.annotate(
        events_count=_count(Event),
        notes_count=_count(Note),
        tasks_count=_count(Task),
    )


class CategoryViewSet(OwnedModelViewSet):
    """Categories group events, notes and tasks. Deleting a category deletes its items."""

    model = Category
    serializer_class = CategorySerializer
    search_fields = ("name", "description")
    ordering_fields = ("name", "created_at", "updated_at")

    def get_queryset(self):
        return with_counts(super().get_queryset())

    def _reload(self, serializer):
        # Re-read the saved object so the response includes the annotated counts.
        serializer.instance = self.get_queryset().get(pk=serializer.instance.pk)

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._reload(serializer)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._reload(serializer)
