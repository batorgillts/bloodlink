from rest_framework.permissions import BasePermission

from accounts.models import User


class IsDonor(BasePermission):
    """US-03 is donor self-service; coordinator edits belong to US-08."""

    message = "Only donors can access their contact information here."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == User.Role.DONOR


class CanViewEligibility(BasePermission):
    """US-04: a donor sees their own eligibility; a coordinator looks up one donor."""

    message = "You cannot view donation eligibility."

    def has_permission(self, request, view):
        user = request.user
        return user.is_authenticated and user.role in (
            User.Role.DONOR,
            User.Role.COORDINATOR,
        )


class CanWithdrawRegistration(BasePermission):
    """US-05: only a donor may withdraw their own registration."""

    message = "Only a donor can withdraw their own registration."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == User.Role.DONOR
