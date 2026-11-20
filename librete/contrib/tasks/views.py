from librete.utils.viewsets import OwnedModelViewSet

from .models import Task
from .serializers import TaskSerializer


class TaskViewSet(OwnedModelViewSet):
    model = Task
    serializer_class = TaskSerializer
    filterset_fields = {
        "category": ["exact"],
        "parent": ["exact", "isnull"],
        "status": ["exact"],
        "priority": ["exact"],
        "start_date": ["gte", "lte"],
        "end_date": ["gte", "lte"],
    }
    search_fields = ("name", "description")
    ordering_fields = (
        "name",
        "priority",
        "status",
        "start_date",
        "end_date",
        "created_at",
        "updated_at",
    )
