from django.contrib import admin
from parler.admin import TranslatableAdmin

from .models import Category, DefaultCategory


@admin.register(DefaultCategory)
class DefaultCategoryAdmin(TranslatableAdmin):
    list_display = ("__str__", "created_at")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "author", "created_at")
    search_fields = ("name", "author__email")
    raw_id_fields = ("author",)
