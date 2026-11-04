from django.contrib import admin

from .models import BloodRequest


@admin.register(BloodRequest)
class BloodRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "blood_type",
        "component",
        "quantity",
        "status",
        "logged_at",
        "logged_by",
    )
    list_filter = ("status", "blood_type", "component")
    readonly_fields = ("logged_at", "logged_by")
