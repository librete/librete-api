from librete.contrib.categories.models import Category
from librete.utils.serializers import OwnedModelSerializer, OwnedPrimaryKeyRelatedField

from .models import Note


class NoteSerializer(OwnedModelSerializer):
    category = OwnedPrimaryKeyRelatedField(queryset=Category.objects.all())

    class Meta:
        model = Note
        fields = ("id", "client_id", "name", "category", "text", "created_at", "updated_at")
