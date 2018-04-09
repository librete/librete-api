from rest_framework import serializers

from django.contrib.auth.models import User


class UserSerializer(serializers.HyperlinkedModelSerializer):
    categories = serializers.HyperlinkedRelatedField(
        many=True,
        read_only=True,
        view_name='category-detail'
    )
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
        model = User
        fields = ('url',
                  'username',
                  'email',
                  'password',
                  'first_name',
                  'last_name',
                  'categories',
                  'events',
                  'notes',
                  'tasks')
        extra_kwargs = {
            'password': {
                'write_only': True
            }
        }

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        instance = self.Meta.model(**validated_data)
        if password is not None:
            instance.set_password(password)
        instance.save()
        return instance
