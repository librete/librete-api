from django.urls import reverse
from django.contrib.auth.models import User

from rest_framework.test import APITestCase

from ..models import Note
from librete.contrib.categories.models import Category
from librete.utils.tests import get_authorization_header, format_datetime


class NoteListTestCase(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('john.doe',
                                             'john.doe@example.com',
                                             'password')
        self.category = Category.objects.create(
            name='Category name',
            description='Category description',
            author=self.user
        )
        self.note = Note.objects.create(name='Note name',
                                        author=self.user,
                                        category=self.category,
                                        text='Note text')
        self.token = get_authorization_header(self.user)

    def test_get(self):
        url = reverse('note-list')
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
                        reverse('note-detail', args=[self.note.pk])),
                    'name': self.note.name,
                    'author': response.wsgi_request.build_absolute_uri(
                        reverse('user-detail', args=[self.user.pk])),
                    'category': response.wsgi_request.build_absolute_uri(
                        reverse('category-detail', args=[self.category.pk])),
                    'text': self.note.text,
                    'created_at': format_datetime(self.note.created_at),
                    'updated_at': format_datetime(self.note.updated_at),
                }
            ],
        }

        self.assertDictEqual(response.json(), expected_response)

    def test_post(self):
        number_of_notes = Note.objects.count()
        url = reverse('note-list')

        data = {
            'name': 'New note name',
            'category': reverse('category-detail',
                                args=[self.category.pk]),
            'text': 'New note text',
        }
        response = self.client.post(url,
                                    data=data,
                                    format='json',
                                    HTTP_AUTHORIZATION=self.token)

        self.assertEqual(response.status_code, 201)

        self.assertEqual(Note.objects.count(), number_of_notes+1)

        note = Note.objects.last()

        expected_response = {
            'url': response.wsgi_request.build_absolute_uri(
                reverse('note-detail', args=[note.pk])),
            'name': data.get('name'),
            'author': response.wsgi_request.build_absolute_uri(
                reverse('user-detail', args=[self.user.pk])),
            'category': response.wsgi_request.build_absolute_uri(
                reverse('category-detail', args=[self.category.pk])),
            'text': data.get('text'),
            'created_at': format_datetime(note.created_at),
            'updated_at': format_datetime(note.updated_at),
        }

        self.assertDictEqual(response.json(), expected_response)
