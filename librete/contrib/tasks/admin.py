from django.contrib import admin

from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("name", "author", "category", "status", "priority", "end_date", "repeat")
    list_filter = ("status", "priority")
    search_fields = ("name", "author__email")
    raw_id_fields = ("author", "category", "parent")
