from django.contrib import admin

from .models import BloodRequest, RequestEvent, Reservation


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


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        "request",
        "unit",
        "reserved_at",
        "reserved_by",
        "released_at",
        "release_reason",
    )
    list_filter = ("release_reason",)
    readonly_fields = (
        "request",
        "unit",
        "reserved_at",
        "reserved_by",
        "released_at",
        "release_reason",
    )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RequestEvent)
class RequestEventAdmin(admin.ModelAdmin):
    list_display = ("request", "event_type", "created_at", "actor", "unit")
    list_filter = ("event_type",)
    readonly_fields = (
        "request",
        "event_type",
        "from_status",
        "to_status",
        "unit",
        "created_at",
        "actor",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
