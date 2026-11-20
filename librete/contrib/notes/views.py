from librete.utils.viewsets import OwnedModelViewSet

from .models import Note
from .serializers import NoteSerializer


class NoteViewSet(OwnedModelViewSet):
    model = Note
    serializer_class = NoteSerializer
    filterset_fields = {
        "category": ["exact"],
        "created_at": ["gte", "lte"],
    }
    search_fields = ("name", "text")
    ordering_fields = ("name", "created_at", "updated_at")
