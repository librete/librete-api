from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth.models import User

from librete.contrib.categories.models import Category
from librete.utils.models import TimestampModel
from .constants import PRIORITY_CHOICES, STATUS_CHOICES, ACTIVE


class Task(TimestampModel):
    name = models.CharField(_('Name'),
                            max_length=254)
    author = models.ForeignKey(User,
                               related_name='tasks',
                               on_delete=models.CASCADE)
    category = models.ForeignKey(Category,
                                 related_name='tasks',
                                 on_delete=models.CASCADE)
    start_date = models.DateTimeField(_('Start date'),
                                      blank=True,
                                      null=True)
    end_date = models.DateTimeField(_('End date'),
                                    blank=True,
                                    null=True)
    description = models.CharField(_('Description'),
                                   max_length=1000,
                                   blank=True)
    parent = models.ForeignKey('self',
                               blank=True,
                               null=True,
                               on_delete=models.CASCADE)
    priority = models.CharField(_('Priority'),
                                max_length=254,
                                choices=PRIORITY_CHOICES,
                                blank=True)
    status = models.CharField(_('Status'),
                              max_length=254,
                              choices=STATUS_CHOICES,
                              default=ACTIVE)

    class Meta:
        ordering = ['created_at']
        verbose_name = _('Task')
        verbose_name_plural = _('Tasks')

    def __str__(self):
        return self.name
