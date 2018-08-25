
from django.forms import Textarea

from parler.forms import TranslatableModelForm

from .models import DefaultCategory


class DefaultCategoryAdminForm(TranslatableModelForm):

    class Meta:
        model = DefaultCategory
        fields = (
            'name',
            'description'
        )
        widgets = {
            'description': Textarea(),
        }
