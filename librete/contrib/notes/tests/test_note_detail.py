from django.urls import reverse
from django.contrib.auth.models import User

from rest_framework.test import APITestCase

from ..models import Note
from librete.contrib.categories.models import Category
from librete.utils.tests import get_authorization_header, format_datetime


class NoteDetailTestCase(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user('john.doe',
                                             'john.doe@example.com',
                                             'password')
        self.category = Category.objects.create(
            name='Category name',
            description='Category description',
            author=self.user)
        self.note = Note.objects.create(name='Note name',
                                        author=self.user,
                                        category=self.category,
                                        text='Note text')
        self.token = get_authorization_header(self.user)

    def test_get(self):
        url = reverse('note-detail', args=[self.note.pk])
        response = self.client.get(url,
                                   format='json',
                                   HTTP_AUTHORIZATION=self.token)

        self.assertEqual(response.status_code, 200)

        expected_response = {
            'url': response.wsgi_request.build_absolute_uri(url),
            'name': self.note.name,
            'author': response.wsgi_request.build_absolute_uri(
                reverse('user-detail', args=[self.user.pk])),
            'category': response.wsgi_request.build_absolute_uri(
                reverse('category-detail', args=[self.category.pk])),
            'text': self.note.text,
            'created_at': format_datetime(self.note.created_at),
            'updated_at': format_datetime(self.note.updated_at),
        }

        self.assertDictEqual(response.json(), expected_response)

    def test_patch(self):
        url = reverse('note-detail', args=[self.note.pk])

        data = {
            'name': 'Changed note name',
            'category': reverse('category-detail',
                                args=[self.category.pk]),
            'text': 'Changed note text',
        }
        response = self.client.patch(url,
                                     data=data,
                                     format='json',
                                     HTTP_AUTHORIZATION=self.token)
        self.assertEqual(response.status_code, 200)

        note = Note.objects.last()

        self.assertNotEqual(note.updated_at, self.note.updated_at)

        expected_response = {
            'url': response.wsgi_request.build_absolute_uri(
                reverse('note-detail', args=[note.pk])),
            'name': data.get('name'),
            'author': response.wsgi_request.build_absolute_uri(
                reverse('user-detail', args=[note.author.pk])),
            'category': response.wsgi_request.build_absolute_uri(
                reverse('category-detail', args=[note.category.pk])),
            'text': data.get('text'),
            'created_at': format_datetime(note.created_at),
            'updated_at': format_datetime(note.updated_at),
        }

        self.assertDictEqual(response.json(), expected_response)

    def test_delete(self):
        url = reverse('note-detail', args=[self.note.pk])

        response = self.client.delete(url,
                                      format='json',
                                      HTTP_AUTHORIZATION=self.token)

        note = Note.objects.filter(pk=self.note.pk).first()

        self.assertEqual(response.status_code, 204)
        self.assertIsNone(note)
