"""US-11 blood request operations."""

from . import repository


def list_blood_requests():
    return repository.list_blood_requests()


def log_blood_request(data, coordinator):
    # Status and logging metadata are assigned by the server, not the client.
    return repository.create_blood_request(logged_by=coordinator, **data)
