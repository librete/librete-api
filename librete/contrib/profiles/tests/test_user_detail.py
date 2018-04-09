
from datetime import timedelta

from django.utils import timezone
from django.urls import reverse
from django.contrib.auth.models import User

from rest_framework.test import APITestCase

from librete.contrib.categories.models import Category
from librete.contrib.events.models import Event
from librete.contrib.notes.models import Note
from librete.contrib.tasks.models import Task
from librete.contrib.tasks.constants import HIGH, ACTIVE
from librete.utils.tests import get_authorization_header


class UserDetailTestCase(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('john.doe',
                                             'john.doe@example.com',
                                             'password',
                                             first_name='John',
                                             last_name='Doe')
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
        url = reverse('user-detail', args=[self.user.pk])
        response = self.client.get(url,
                                   format='json',
                                   HTTP_AUTHORIZATION=self.token)

        self.assertEqual(response.status_code, 200)

        expected_response = {
            'url': response.wsgi_request.build_absolute_uri(url),
            'username': self.user.username,
            'email': self.user.email,
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
            'categories': [
                response.wsgi_request.build_absolute_uri(
                    reverse('category-detail',
                            args=[self.category.pk])),
            ],
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
        }

        self.assertDictEqual(response.json(), expected_response)

    def test_put(self):
        url = reverse('user-detail', args=[self.user.pk])

        data = {
            'username': 'richard.roe',
            'email': 'richard.roe@example.com',
            'current_password': 'password',
            'first_name': 'Richard',
            'last_name': 'Roe',
        }

        response = self.client.put(url,
                                   data=data,
                                   format='json',
                                   HTTP_AUTHORIZATION=self.token)
        self.assertEqual(response.status_code, 200)

        user = User.objects.last()

        expected_response = {
            'url': response.wsgi_request.build_absolute_uri(
                reverse('user-detail', args=[user.pk])),
            'username': self.user.username,
            'email': data.get('email'),
            'first_name': data.get('first_name'),
            'last_name': data.get('last_name'),
            'categories': [
                response.wsgi_request.build_absolute_uri(
                    reverse('category-detail',
                            args=[self.category.pk])),
            ],
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
        }

        self.assertDictEqual(response.json(), expected_response)

        # Test if username is changed
        self.assertEqual(user.username, self.user.username)

    def test_delete(self):
        url = reverse('user-detail', args=[self.user.pk])

        response = self.client.delete(url,
                                      format='json',
                                      HTTP_AUTHORIZATION=self.token)

        user = User.objects.filter(pk=self.user.pk).first()

        self.assertEqual(response.status_code, 204)
        self.assertIsNone(user)
