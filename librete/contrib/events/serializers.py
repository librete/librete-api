from rest_framework import serializers

from .models import Event


class EventSerializer(serializers.HyperlinkedModelSerializer):
    author = serializers.HyperlinkedRelatedField(read_only=True,
                                                 view_name='user-detail')

    class Meta:
        model = Event
        fields = '__all__'
