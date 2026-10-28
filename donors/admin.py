from django.contrib import admin

from .models import Donor


@admin.register(Donor)
class DonorAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "blood_type", "phone", "status")
    list_filter = ("blood_type", "status")
    search_fields = ("full_name", "user__email")
