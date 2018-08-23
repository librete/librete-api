from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _

from parler.models import TranslatableModel, TranslatedFields

from librete.utils.models import TimestampModel


class Category(TimestampModel):
    name = models.CharField(_('Name'),
                            max_length=254)
    author = models.ForeignKey(User,
                               related_name='categories',
                               on_delete=models.CASCADE)
    description = models.CharField(_('Description'),
                                   max_length=1000,
                                   blank=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = _('Category')
        verbose_name_plural = _('Categories')

    def __str__(self):
        return self.name

class DefaultCategory(TranslatableModel, TimestampModel):
    translations = TranslatedFields(
        name=models.CharField(_('Name'),
                              max_length=254),
        description=models.CharField(_('Description'),
                                     max_length=1000,
                                     blank=True)
    )

    class Meta:
        ordering = ['created_at']
        verbose_name = _('Default category')
        verbose_name_plural = _('Default categories')

    def __str__(self):
        return self.name
