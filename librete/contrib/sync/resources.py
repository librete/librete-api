"""The synced resources: change-log type, model, serializer and queryset of each."""

from dataclasses import dataclass

from librete.contrib.categories.models import Category
from librete.contrib.categories.serializers import CategorySerializer
from librete.contrib.categories.views import with_counts
from librete.contrib.events.models import Event
from librete.contrib.events.serializers import EventSerializer
from librete.contrib.notes.models import Note
from librete.contrib.notes.serializers import NoteSerializer
from librete.contrib.tasks.models import Task
from librete.contrib.tasks.serializers import TaskSerializer

from .models import Change


@dataclass(frozen=True)
class Resource:
    type: str
    model: type
    serializer_class: type
    annotate: object = None

    def queryset(self, user):
        """The user's objects, prepared exactly like the resource's viewset does."""
        queryset = self.model.objects.filter(author=user)
        return self.annotate(queryset) if self.annotate else queryset


RESOURCES = {
    resource.type: resource
    for resource in (
        Resource(Change.Type.CATEGORIES, Category, CategorySerializer, with_counts),
        Resource(Change.Type.EVENTS, Event, EventSerializer),
        Resource(Change.Type.NOTES, Note, NoteSerializer),
        Resource(Change.Type.TASKS, Task, TaskSerializer),
    )
}
TYPE_BY_MODEL = {resource.model: resource.type for resource in RESOURCES.values()}
