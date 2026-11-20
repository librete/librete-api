from django.db import models
from django.utils.translation import gettext_lazy as _
from parler.models import TranslatableModel, TranslatedFields

from librete.utils.models import OwnedModel, TimestampModel


class Category(OwnedModel):
    name = models.CharField(_("Name"), max_length=254)
    description = models.TextField(_("Description"), blank=True)

    class Meta(OwnedModel.Meta):
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")

    def __str__(self):
        return self.name


class DefaultCategory(TranslatableModel, TimestampModel):
    """Template categories copied to every new user, in the user's language."""

    translations = TranslatedFields(
        name=models.CharField(_("Name"), max_length=254),
        description=models.TextField(_("Description"), blank=True),
    )

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("Default category")
        verbose_name_plural = _("Default categories")

    def __str__(self):
        return self.safe_translation_getter("name", any_language=True) or ""
