from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from parler.models import TranslatableModel, TranslatedFields

from librete.utils.models import OwnedModel, TimestampModel


class Category(OwnedModel):
    name = models.CharField(_("Name"), max_length=254)
    description = models.TextField(_("Description"), blank=True)
    # null (not "") means "no colour": the API contract returns `null`.
    color = models.CharField(  # noqa: DJ001
        _("Color"),
        max_length=7,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                r"^#[0-9a-f]{6}$", _("Enter a color in the #RRGGBB format."), code="invalid"
            )
        ],
        help_text=_("Hex color such as #1e88e5, stored in lower case."),
    )

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
