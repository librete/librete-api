from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth.models import User

from librete.contrib.categories.models import Category
from librete.utils.models import TimestampModel


class Note(TimestampModel):
    name = models.CharField(_('Name'),
                            max_length=254)
    author = models.ForeignKey(User,
                               related_name='notes',
                               on_delete=models.CASCADE)
    category = models.ForeignKey(Category,
                                 related_name='notes',
                                 on_delete=models.CASCADE)
    text = models.CharField(_('Text'),
                            max_length=1000)

    class Meta:
        ordering = ['created_at']
        verbose_name = _('Note')
        verbose_name_plural = _('Notes')

    def __str__(self):
        return self.name
