from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _

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
