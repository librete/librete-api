from django.contrib import admin

from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("name", "author", "category", "start_date", "end_date", "recurrence")
    list_filter = ("start_date",)
    search_fields = ("name", "author__email")
    raw_id_fields = ("author", "category", "recurrence_parent")
