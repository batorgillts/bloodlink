from django.contrib import admin

from .models import BloodUnit, ShelfLifeRule


@admin.register(BloodUnit)
class BloodUnitAdmin(admin.ModelAdmin):
    list_display = ("unit_code", "blood_type", "component", "status", "expires_at")
    list_filter = ("component", "blood_type", "status")
    search_fields = ("unit_code",)


admin.site.register(ShelfLifeRule)
