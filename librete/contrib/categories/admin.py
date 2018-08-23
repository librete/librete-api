from django.contrib import admin

from parler.admin import TranslatableAdmin

from .models import DefaultCategory
from .forms import DefaultCategoryAdminForm


@admin.register(DefaultCategory)
class DefaultCategoryAdmin(TranslatableAdmin):
    form = DefaultCategoryAdminForm
