from datetime import timedelta

from django.utils import timezone
from django.urls import reverse
from django.contrib.auth.models import User

from rest_framework.test import APITestCase

from ..models import Category
from librete.contrib.events.models import Event
from librete.contrib.notes.models import Note
from librete.contrib.tasks.models import Task
from librete.contrib.tasks.constants import HIGH, ACTIVE

from librete.utils.tests import get_authorization_header, format_datetime


class CategoryListTestCase(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('john.doe',
                                             'john.doe@example.com',
                                             'password')
        self.category = Category.objects.create(
            name='Category name',
            description='Category description',
            author=self.user
        )
        start_date = timezone.now() + timedelta(days=5)
        end_date = timezone.now() + timedelta(days=5, hours=2)
        self.event = Event.objects.create(name='Event name',
                                          author=self.user,
                                          category=self.category,
                                          location='Event location',
                                          description='Event description',
                                          start_date=start_date,
                                          end_date=end_date)
        self.note = Note.objects.create(name='Note name',
                                        author=self.user,
                                        category=self.category,
                                        text='Note text')
        self.task = Task.objects.create(name='Task name',
                                        author=self.user,
                                        category=self.category,
                                        description='Task description',
                                        parent=None,
                                        priority=HIGH,
                                        status=ACTIVE,
                                        start_date=start_date,
                                        end_date=end_date)
        self.token = get_authorization_header(self.user)

    def test_get(self):
        url = reverse('category-list')
        response = self.client.get(url,
                                   format='json',
                                   HTTP_AUTHORIZATION=self.token)
        self.assertEqual(response.status_code, 200)

        expected_response = {
            'count': 1,
            'next': None,
            'previous': None,
            'results': [
                {
                    'url': response.wsgi_request.build_absolute_uri(
                        reverse('category-detail', args=[self.category.pk])),
                    'name': self.category.name,
                    'description': self.category.description,
                    'author': response.wsgi_request.build_absolute_uri(
                        reverse('user-detail', args=[self.user.pk])),
                    'updated_at': format_datetime(self.category.updated_at),
                    'created_at': format_datetime(self.category.created_at),
                    'events': [
                        response.wsgi_request.build_absolute_uri(
                            reverse('event-detail', args=[self.event.pk])),
                    ],
                    'notes': [
                        response.wsgi_request.build_absolute_uri(
                            reverse('note-detail', args=[self.note.pk])),
                    ],
                    'tasks': [
                        response.wsgi_request.build_absolute_uri(
                            reverse('task-detail', args=[self.task.pk])),
                    ],
                },
            ],
        }

        self.assertDictEqual(response.json(), expected_response)

    def test_post(self):
        number_of_categories = Category.objects.count()
        url = reverse('category-list')

        data = {
            'name': 'New category name',
            'description': 'New category description',
        }
        response = self.client.post(url,
                                    data=data,
                                    format='json',
                                    HTTP_AUTHORIZATION=self.token)

        self.assertEqual(response.status_code, 201)

        self.assertEqual(Category.objects.count(), number_of_categories+1)

        category = Category.objects.last()

        expected_response = {
            'url': response.wsgi_request.build_absolute_uri(
                reverse('category-detail', args=[category.pk])),
            'name': data.get('name'),
            'author': response.wsgi_request.build_absolute_uri(
                reverse('user-detail', args=[self.user.pk])),
            'description': data.get('description'),
            'updated_at': format_datetime(category.updated_at),
            'created_at': format_datetime(category.created_at),
            'events': [],
            'notes': [],
            'tasks': [],
        }
        self.maxDiff = None
        self.assertDictEqual(response.json(), expected_response)
