from rest_framework import viewsets


class OwnedModelViewSet(viewsets.ModelViewSet):
    """CRUD restricted to the requesting user's own records."""

    model = None

    def get_queryset(self):
        return self.model.objects.filter(author=self.request.user)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
