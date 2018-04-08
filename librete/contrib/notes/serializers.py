from rest_framework import serializers

from .models import Note


class NoteSerializer(serializers.HyperlinkedModelSerializer):
    author = serializers.HyperlinkedRelatedField(read_only=True,
                                                 view_name='user-detail')

    class Meta:
        model = Note
        fields = '__all__'
