from django.db import models
from django.utils.translation import gettext_lazy as _

from librete.contrib.categories.models import Category
from librete.utils.models import OwnedModel


class Note(OwnedModel):
    name = models.CharField(_("Name"), max_length=254)
    category = models.ForeignKey(
        Category, verbose_name=_("Category"), related_name="notes", on_delete=models.CASCADE
    )
    text = models.TextField(_("Text"))

    class Meta(OwnedModel.Meta):
        verbose_name = _("Note")
        verbose_name_plural = _("Notes")

    def __str__(self):
        return self.name
