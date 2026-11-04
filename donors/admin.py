from django.contrib import admin

from .models import Donation, DonationIntervalRule, Donor


@admin.register(Donor)
class DonorAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "blood_type", "phone", "status")
    list_filter = ("blood_type", "status")
    search_fields = ("full_name", "user__email")


@admin.register(DonationIntervalRule)
class DonationIntervalRuleAdmin(admin.ModelAdmin):
    list_display = ("donation_type", "min_interval_days")


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = (
        "donor",
        "donation_type",
        "donation_date",
        "blood_type",
        "volume_ml",
        "recorded_by",
    )
    list_filter = ("donation_type", "blood_type")
    search_fields = ("donor__full_name", "donor__user__email")
