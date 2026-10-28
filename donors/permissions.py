from rest_framework.permissions import BasePermission

from accounts.models import User


class IsDonor(BasePermission):
    """US-03 is donor self-service; coordinator edits belong to US-08."""

    message = "Only donors can access their contact information here."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == User.Role.DONOR
