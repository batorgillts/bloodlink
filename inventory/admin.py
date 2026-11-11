from django.contrib import admin

from .models import BloodUnit, ShelfLifeRule


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
