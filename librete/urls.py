from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from .contrib.categories.views import CategoryViewSet
from .contrib.events.views import EventViewSet
from .contrib.notes.views import NoteViewSet
from .contrib.reminders.views import PushSubscriptionViewSet, VapidKeyView
from .contrib.search.views import SearchView
from .contrib.stats.views import StatsView
from .contrib.sync.views import SyncView
from .contrib.tasks.views import TaskViewSet
from .contrib.users.views import AccountDeleteView, MeView

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("events", EventViewSet, basename="event")
router.register("notes", NoteViewSet, basename="note")
router.register("tasks", TaskViewSet, basename="task")
router.register("push/subscriptions", PushSubscriptionViewSet, basename="push-subscription")


def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("api/push/vapid-key/", VapidKeyView.as_view(), name="push-vapid-key"),
    path("api/", include(router.urls)),
    path("api/users/me/", MeView.as_view(), name="user-me"),
    path("api/users/me/delete/", AccountDeleteView.as_view(), name="user-delete"),
    path("api/stats/", StatsView.as_view(), name="stats"),
    path("api/sync/", SyncView.as_view(), name="sync"),
    path("api/search/", SearchView.as_view(), name="search"),
    path("api/health/", health, name="health"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("_allauth/", include("allauth.headless.urls")),
    path("admin/", admin.site.urls),
]
