from rest_framework import viewsets

from librete.utils.permissions import IsAuthor
from .models import Task
from .serializers import TaskSerializer


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def get_queryset(self):
        return Task.objects.all().filter(author=self.request.user)

    def get_permissions(self):
        permission_classes = super().get_permissions()
        permission_classes.append(IsAuthor())
        return permission_classes
