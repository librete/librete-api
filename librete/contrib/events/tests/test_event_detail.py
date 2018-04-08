from datetime import timedelta

from django.utils import timezone
from django.urls import reverse
from django.contrib.auth.models import User

from rest_framework.test import APITestCase

from ..models import Event
from librete.contrib.categories.models import Category
from librete.utils.tests import get_authorization_header, format_datetime


class EventDetailTestCase(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('john.doe',
                                             'john.doe@example.com',
                                             'password')
        self.category = Category.objects.create(
            name='Category name',
            description='Category description',
            author=self.user)
        start_date = timezone.now() + timedelta(days=5)
        end_date = timezone.now() + timedelta(days=5, hours=2)
        self.event = Event.objects.create(name='Event name',
                                          author=self.user,
                                          category=self.category,
                                          location='Event location',
                                          description='Event description',
                                          start_date=start_date,
                                          end_date=end_date)
        self.token = get_authorization_header(self.user)

    def test_get(self):
        url = reverse('event-detail', args=[self.event.pk])
        response = self.client.get(url,
                                   format='json',
                                   HTTP_AUTHORIZATION=self.token)

        self.assertEqual(response.status_code, 200)

        expected_response = {
            'url': response.wsgi_request.build_absolute_uri(url),
            'name': self.event.name,
            'author': response.wsgi_request.build_absolute_uri(
                reverse('user-detail', args=[self.user.pk])),
            'category': response.wsgi_request.build_absolute_uri(
                reverse('category-detail', args=[self.category.pk])),
            'location': self.event.location,
            'description': self.event.description,
            'start_date': format_datetime(self.event.start_date),
            'end_date': format_datetime(self.event.end_date),
            'created_at': format_datetime(self.event.created_at),
            'updated_at': format_datetime(self.event.updated_at),
        }

        self.assertDictEqual(response.json(), expected_response)

    def test_patch(self):
        url = reverse('event-detail', args=[self.event.pk])

        start_date = timezone.now() + timedelta(days=7)
        end_date = timezone.now() + timedelta(days=7, hours=5)

        data = {
            'name': 'Changed event name',
            'category': reverse('category-detail',
                                args=[self.category.pk]),
            'location': 'Changed event location',
            'description': 'Changed event description',
            'start_date': start_date,
            'end_date': end_date,
        }
        response = self.client.patch(url,
                                     data=data,
                                     format='json',
                                     HTTP_AUTHORIZATION=self.token)
        self.assertEqual(response.status_code, 200)

        event = Event.objects.last()

        self.assertNotEqual(event.updated_at, self.event.updated_at)

        expected_response = {
            'url': response.wsgi_request.build_absolute_uri(
                reverse('event-detail', args=[event.pk])),
            'name': data.get('name'),
            'author': response.wsgi_request.build_absolute_uri(
                reverse('user-detail', args=[event.author.pk])),
            'category': response.wsgi_request.build_absolute_uri(
                reverse('category-detail', args=[event.category.pk])),
            'location': data.get('location'),
            'description': data.get('description'),
            'start_date': format_datetime(data.get('start_date')),
            'end_date': format_datetime(data.get('end_date')),
            'created_at': format_datetime(event.created_at),
            'updated_at': format_datetime(event.updated_at),
        }

        self.assertDictEqual(response.json(), expected_response)

    def test_delete(self):
        url = reverse('event-detail', args=[self.event.pk])

        response = self.client.delete(url,
                                      format='json',
                                      HTTP_AUTHORIZATION=self.token)

        event = Event.objects.filter(pk=self.event.pk).first()

        self.assertEqual(response.status_code, 204)
        self.assertIsNone(event)
