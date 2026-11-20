from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import AccountDeleteSerializer, UserSerializer


class MeView(generics.RetrieveUpdateAPIView):
    """The authenticated user's profile. Email and password are managed via allauth."""

    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class AccountDeleteView(APIView):
    """Permanently delete the authenticated user's account and all of their data."""

    @extend_schema(request=AccountDeleteSerializer, responses={204: None})
    def post(self, request):
        serializer = AccountDeleteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
