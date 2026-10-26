from rest_framework.permissions import BasePermission


# For NFR decision: rike checks happen on the server for every request, never only by hiding buttons.
class IsCoordinator(BasePermission):
    """Coordinator-only endpoints. Signed-in donors get 403 (NFR-5)."""

    message = "Only coordinators can do this."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_coordinator)
