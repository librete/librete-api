from rest_framework import serializers

from .models import Category


class CategorySerializer(serializers.HyperlinkedModelSerializer):
    author = serializers.HyperlinkedRelatedField(read_only=True,
                                                 view_name='user-detail')
    events = serializers.HyperlinkedRelatedField(many=True,
                                                 read_only=True,
                                                 view_name='event-detail')
    notes = serializers.HyperlinkedRelatedField(many=True,
                                                read_only=True,
                                                view_name='note-detail')
    tasks = serializers.HyperlinkedRelatedField(many=True,
                                                read_only=True,
                                                view_name='task-detail')

    class Meta:
        model = Category
        fields = '__all__'

