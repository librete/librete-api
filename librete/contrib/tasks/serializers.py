from rest_framework import serializers

from .models import Task


class TaskSerializer(serializers.HyperlinkedModelSerializer):
    author = serializers.HyperlinkedRelatedField(read_only=True,
                                                 view_name='user-detail')

    class Meta:
        model = Task
        fields = '__all__'
