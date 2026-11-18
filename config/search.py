from django.db.models import Q


def filter_text(queryset, text, fields):
    """Case-insensitive partial matching; every word may match any searchable field."""
    for word in (text or "").split():
        matches = Q()
        for field in fields:
            matches |= Q(**{f"{field}__icontains": word})
        queryset = queryset.filter(matches)
    return queryset
