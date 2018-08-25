from django.contrib.auth.models import User

from rest_framework import serializers

from librete.contrib.categories.models import Category, DefaultCategory


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
        for category in DefaultCategory.objects.all():
            Category.objects.create(name=category.name,
                                    author=instance,
                                    description=category.description)
        return instance


class UserUpdateSerializer(serializers.HyperlinkedModelSerializer):
    current_password = serializers.CharField(max_length=128,
                                             write_only=True)
    new_password = serializers.CharField(max_length=128,
                                         write_only=True,
                                         required=False)
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
                  'current_password',
                  'new_password',
                  'first_name',
                  'last_name',
                  'categories',
                  'events',
                  'notes',
                  'tasks')
        extra_kwargs = {
            'username': {
                'read_only': True
            }
        }

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            if attr == 'new_password' and value:
                instance.set_password(value)
            else:
                setattr(instance, attr, value)
        instance.save()
        return instance

    def validate_current_password(self, value):
        if not self.instance.check_password(value):
            raise serializers.ValidationError('Invalid password')
        return value
