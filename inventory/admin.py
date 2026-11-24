from django.contrib import admin

from .models import BloodUnit, ShelfLifeRule, StockThreshold


@admin.register(BloodUnit)
class BloodUnitAdmin(admin.ModelAdmin):
    list_display = (
        "unit_code",
        "blood_type",
        "component",
        "status",
        "expires_at",
        "discard_reason",
        "discarded_at",
    )
    list_filter = ("component", "blood_type", "status", "discard_reason")
    readonly_fields = ("status", "discard_reason", "discarded_at", "discarded_by")
    search_fields = ("unit_code",)


admin.site.register(ShelfLifeRule)


@admin.register(StockThreshold)
class StockThresholdAdmin(admin.ModelAdmin):
    list_display = ("blood_type", "component", "minimum_units", "expiring_soon_days", "updated_at")
    list_filter = ("component", "blood_type")
