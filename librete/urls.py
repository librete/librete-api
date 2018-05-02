"""librete URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

from rest_framework.routers import DefaultRouter
from rest_framework.documentation import include_docs_urls

from .contrib.profiles.views import UserViewSet
from .contrib.events.views import EventViewSet
from .contrib.notes.views import NoteViewSet
from .contrib.tasks.views import TaskViewSet
from .contrib.categories.views import CategoryViewSet


router = DefaultRouter()
router.register(r'users', UserViewSet, base_name='user')
router.register(r'events', EventViewSet, base_name='event')
router.register(r'notes', NoteViewSet, base_name='note')
router.register(r'tasks', TaskViewSet, base_name='task')
router.register(r'categories', CategoryViewSet, base_name='category')

urlpatterns = [
  path('api/', include(router.urls)),
  path('api/oauth2/', include('oauth2_provider.urls', namespace='oauth2_provider')),
  path('admin/', admin.site.urls),
  path('docs/', include_docs_urls(title='Lirete API', public=False)),
]
