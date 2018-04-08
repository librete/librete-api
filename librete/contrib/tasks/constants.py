from django.utils.translation import ugettext_lazy as _


HIGH = 'high'
MEDIUM = 'medium'
LOW = 'low'

PRIORITY_CHOICES = (
    (HIGH, _('High')),
    (MEDIUM, _('Medium')),
    (LOW, _('Low')),
)


ACTIVE = 'active'
FINISHED = 'finished'

STATUS_CHOICES = (
    (ACTIVE, _('Active')),
    (FINISHED, _('Finished')),
)
