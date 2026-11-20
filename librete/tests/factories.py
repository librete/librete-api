from datetime import timedelta

import factory
from django.utils import timezone

from librete.contrib.categories.models import Category
from librete.contrib.events.models import Event
from librete.contrib.notes.models import Note
from librete.contrib.tasks.models import Task
from librete.contrib.users.models import User

PASSWORD = "correct-horse-battery-staple"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = "John"
    last_name = "Doe"
    password = factory.django.Password(PASSWORD)


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    author = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Category {n}")
    description = "Category description"


class EventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Event

    author = factory.SubFactory(UserFactory)
    category = factory.SubFactory(CategoryFactory, author=factory.SelfAttribute("..author"))
    name = factory.Sequence(lambda n: f"Event {n}")
    start_date = factory.LazyFunction(lambda: timezone.now() + timedelta(days=5))
    end_date = factory.LazyAttribute(lambda o: o.start_date + timedelta(hours=2))
    location = "Sofia"
    description = "Event description"


class NoteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Note

    author = factory.SubFactory(UserFactory)
    category = factory.SubFactory(CategoryFactory, author=factory.SelfAttribute("..author"))
    name = factory.Sequence(lambda n: f"Note {n}")
    text = "Note text"


class TaskFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Task

    author = factory.SubFactory(UserFactory)
    category = factory.SubFactory(CategoryFactory, author=factory.SelfAttribute("..author"))
    name = factory.Sequence(lambda n: f"Task {n}")
    description = "Task description"
    priority = Task.Priority.HIGH
    status = Task.Status.ACTIVE
