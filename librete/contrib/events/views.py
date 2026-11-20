from librete.utils.viewsets import OwnedModelViewSet

from .models import Event
from .serializers import EventSerializer


class EventViewSet(OwnedModelViewSet):
    model = Event
    serializer_class = EventSerializer
    filterset_fields = {
        "category": ["exact"],
        "start_date": ["gte", "lte"],
        "end_date": ["gte", "lte"],
    }
    search_fields = ("name", "location", "description")
    ordering_fields = ("name", "start_date", "end_date", "created_at", "updated_at")
