"""Explainable 12-week request-demand forecast using ordinary least squares."""

from datetime import timedelta

from django.utils import timezone

from config.choices import BloodType, Component
from request.models import BloodRequest

HISTORY_WEEKS = 12
MIN_HISTORY_WEEKS = 4


def _week_start(value):
    return value - timedelta(days=value.weekday())


def _linear_regression_forecast(values):
    """Fit y = intercept + slope*x by OLS and predict the week after the last point."""
    count = len(values)
    if not count:
        return 0.0

    x_mean = (count - 1) / 2
    y_mean = sum(values) / count
    denominator = sum((x - x_mean) ** 2 for x in range(count))
    slope = (
        sum((x - x_mean) * (value - y_mean) for x, value in enumerate(values)) / denominator
        if denominator
        else 0.0
    )
    return max(0.0, y_mean + slope * (count - x_mean))


def weekly_demand_forecast():
    """Return next-week forecasts and their weekly history by blood type/component."""
    today = timezone.localdate()
    current_week = _week_start(today)
    first_week = current_week - timedelta(weeks=HISTORY_WEEKS - 1)
    next_week = current_week + timedelta(weeks=1)

    # Every status except cancelled is demand, including pending, partial and fulfilled.
    weekly_totals = {}
    requests = BloodRequest.objects.exclude(status=BloodRequest.Status.CANCELLED)
    records = requests.filter(
        logged_at__date__gte=first_week,
        logged_at__date__lt=next_week,
    ).values_list("blood_type", "component", "quantity", "logged_at")
    for blood_type, component, quantity, logged_at in records.iterator():
        week = _week_start(timezone.localtime(logged_at).date())
        key = (blood_type, component, week)
        weekly_totals[key] = weekly_totals.get(key, 0) + quantity

    earliest_request = (
        BloodRequest.objects.order_by("logged_at").values_list("logged_at", flat=True).first()
    )
    if earliest_request is None:
        coverage_start_week = None
        available_history_weeks = 0
    else:
        first_record_week = _week_start(timezone.localtime(earliest_request).date())
        coverage_start_week = max(first_week, first_record_week)
        available_history_weeks = max(
            0,
            min(HISTORY_WEEKS, ((current_week - coverage_start_week).days // 7) + 1),
        )

    predictions = []
    for component in Component.values:
        for blood_type in BloodType.values:
            values = []
            history = []
            for offset in range(HISTORY_WEEKS):
                week = first_week + timedelta(weeks=offset)
                covered = coverage_start_week is not None and week >= coverage_start_week
                quantity = weekly_totals.get((blood_type, component, week), 0) if covered else None
                values.append(quantity or 0)
                history.append({"week_start": week.isoformat(), "quantity": quantity})

            enough_history = available_history_weeks >= MIN_HISTORY_WEEKS
            if not enough_history:
                predicted = None
            else:
                # Ignore weeks before data coverage, but retain observed zero-demand weeks.
                training_values = values[-available_history_weeks:]
                predicted = _linear_regression_forecast(training_values)

            predictions.append(
                {
                    "blood_type": blood_type,
                    "component": component,
                    "history": history,
                    "predicted_demand": round(predicted, 2) if predicted is not None else None,
                }
            )

    if available_history_weeks < MIN_HISTORY_WEEKS:
        history_status = "insufficient_history"
    elif available_history_weeks < HISTORY_WEEKS:
        history_status = "limited_history"
    else:
        history_status = "ready"

    return {
        "week_start": next_week.isoformat(),
        "week_end": (next_week + timedelta(days=6)).isoformat(),
        "history_weeks_used": available_history_weeks,
        "minimum_history_weeks": MIN_HISTORY_WEEKS,
        "history_status": history_status,
        "predictions": predictions,
    }
