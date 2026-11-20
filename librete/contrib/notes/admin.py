from django.contrib import admin

from .models import Note


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("name", "author", "category", "created_at")
    search_fields = ("name", "author__email")
    raw_id_fields = ("author", "category")
