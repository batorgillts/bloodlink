from rest_framework import status
from rest_framework.exceptions import APIException


# Sprint 2 error table maps duplicates and conflicts to 409
class Conflict(APIException):
    """409: duplicate or conflicting operation (Sprint 2 error table)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This conflicts with an existing record."
    default_code = "conflict"
