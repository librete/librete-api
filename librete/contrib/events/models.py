from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth.models import User

from librete.contrib.categories.models import Category
from librete.utils.models import TimestampModel


class Event(TimestampModel):
    name = models.CharField(_('Name'),
                            max_length=254)
    author = models.ForeignKey(User,
                               related_name='events',
                               on_delete=models.CASCADE)
    category = models.ForeignKey(Category,
                                 related_name='events',
                                 on_delete=models.CASCADE)
    start_date = models.DateTimeField(_('Start date'))
    end_date = models.DateTimeField(_('End date'))
    location = models.CharField(_('Location'),
                                max_length=254)
    description = models.CharField(_('Description'),
                                   max_length=1000,
                                   blank=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = _('Event')
        verbose_name_plural = _('Events')

    def __str__(self):
        return self.name
