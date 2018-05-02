from django.contrib.auth.models import User

from rest_framework import viewsets

from .serializers import UserSerializer, UserUpdateSerializer


class UserViewSet(viewsets.ModelViewSet):
    """
    This viewset automatically provides `list` and `detail` actions.
    """
    queryset = User.objects.order_by('date_joined')
    serializer_class = UserSerializer
    http_method_names = ['get', 'post', 'put', 'delete']

    def get_serializer_class(self):
        serializer_class = self.serializer_class

        if self.request.method == 'PUT':
            serializer_class = UserUpdateSerializer

        return serializer_class

    def get_authenticators(self):
        if self.request.method == 'POST':
            return []
        return super().get_authenticators()

    def get_permissions(self):
        if self.request.method == 'POST':
            return []
        return super().get_permissions()
