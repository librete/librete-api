from django.contrib import admin

from .models import ScheduledReminder


@admin.register(ScheduledReminder)
class ScheduledReminderAdmin(admin.ModelAdmin):
    list_display = ("event", "minutes_before", "remind_at", "sent_at")
    list_filter = ("sent_at",)
    search_fields = ("event__name", "event__author__email")
    raw_id_fields = ("event",)
