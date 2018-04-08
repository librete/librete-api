
from datetime import timedelta

from django.utils import timezone
from django.urls import reverse
from django.contrib.auth.models import User

from rest_framework.test import APITestCase

from ..models import Task
from ..constants import HIGH, ACTIVE
from librete.contrib.categories.models import Category
from librete.utils.tests import get_authorization_header, format_datetime


class TaskDetailTestCase(APITestCase):

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
        url = reverse('task-detail', args=[self.task.pk])
        response = self.client.get(url,
                                   format='json',
                                   HTTP_AUTHORIZATION=self.token)

        self.assertEqual(response.status_code, 200)

        expected_response = {
            'url': response.wsgi_request.build_absolute_uri(url),
            'name': self.task.name,
            'author': response.wsgi_request.build_absolute_uri(
                reverse('user-detail', args=[self.user.pk])),
            'category': response.wsgi_request.build_absolute_uri(
                reverse('category-detail', args=[self.category.pk])),
            'description': self.task.description,
            'parent': self.task.parent,
            'priority': self.task.priority,
            'status': self.task.status,
            'start_date': format_datetime(self.task.start_date),
            'end_date': format_datetime(self.task.end_date),
            'created_at': format_datetime(self.task.created_at),
            'updated_at': format_datetime(self.task.updated_at),
        }

        self.assertDictEqual(response.json(), expected_response)

    def test_patch(self):
        url = reverse('task-detail', args=[self.task.pk])

        start_date = timezone.now() + timedelta(days=7)
        end_date = timezone.now() + timedelta(days=7, hours=5)

        data = {
            'name': 'Changed task name',
            'category': reverse('category-detail',
                                args=[self.category.pk]),
            'description': 'Changed task description',
            'parent': None,
            'priority': HIGH,
            'status': ACTIVE,
            'start_date': start_date,
            'end_date': end_date,
        }
        response = self.client.patch(url,
                                     data=data,
                                     format='json',
                                     HTTP_AUTHORIZATION=self.token)
        self.assertEqual(response.status_code, 200)

        task = Task.objects.last()

        self.assertNotEqual(task.updated_at, self.task.updated_at)

        expected_response = {
            'url': response.wsgi_request.build_absolute_uri(
                reverse('task-detail', args=[task.pk])),
            'name': data.get('name'),
            'author': response.wsgi_request.build_absolute_uri(
                reverse('user-detail', args=[task.author.pk])),
            'category': response.wsgi_request.build_absolute_uri(
                reverse('category-detail', args=[task.category.pk])),
            'description': data.get('description'),
            'parent': task.parent,
            'priority': task.priority,
            'status': task.status,
            'start_date': format_datetime(data.get('start_date')),
            'end_date': format_datetime(data.get('end_date')),
            'created_at': format_datetime(task.created_at),
            'updated_at': format_datetime(task.updated_at),
        }

        self.assertDictEqual(response.json(), expected_response)

    def test_delete(self):
        url = reverse('task-detail', args=[self.task.pk])

        response = self.client.delete(url,
                                      format='json',
                                      HTTP_AUTHORIZATION=self.token)

        task = Task.objects.filter(pk=self.task.pk).first()

        self.assertEqual(response.status_code, 204)
        self.assertIsNone(task)
