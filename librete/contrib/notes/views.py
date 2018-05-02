from rest_framework import viewsets

from librete.utils.permissions import IsAuthor
from .models import Note
from .serializers import NoteSerializer


class NoteViewSet(viewsets.ModelViewSet):
    serializer_class = NoteSerializer

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def get_queryset(self):
        return Note.objects.all().filter(author=self.request.user)

    def get_permissions(self):
        permission_classes = super().get_permissions()
        permission_classes.append(IsAuthor())
        return permission_classes
