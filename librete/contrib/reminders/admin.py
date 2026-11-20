from django.contrib import admin

from .models import PushSubscription, ScheduledReminder


@admin.register(ScheduledReminder)
class ScheduledReminderAdmin(admin.ModelAdmin):
    list_display = ("event", "minutes_before", "remind_at", "sent_at")
    list_filter = ("sent_at",)
    search_fields = ("event__name", "event__author__email")
    raw_id_fields = ("event",)


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "user_agent", "created_at", "last_used_at")
    search_fields = ("user__email", "endpoint", "user_agent")
    raw_id_fields = ("user",)
    readonly_fields = ("created_at", "last_used_at")
