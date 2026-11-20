from rest_framework import serializers

from librete.contrib.categories.models import Category
from librete.utils.serializers import OwnedPrimaryKeyRelatedField

from .models import Note


class NoteSerializer(serializers.ModelSerializer):
    category = OwnedPrimaryKeyRelatedField(queryset=Category.objects.all())

    class Meta:
        model = Note
        fields = ("id", "name", "category", "text", "created_at", "updated_at")
