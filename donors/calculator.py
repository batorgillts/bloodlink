"""Eligibility Calculator (Sprint 2 C4). No HTTP and no database access.

Next eligible date = latest donation of that type + that type's interval.
A type the donor has never given is eligible on the date being checked.
The donor is eligible on the next eligible date itself (today >= that date).
"""

from datetime import timedelta


def calculate_eligibility(rules, donations, today):
    """One result per configured rule, in the same order as `rules`.

    rules: sequence of (donation_type, min_interval_days).
    donations: sequence of (donation_type, donation_date).
    today: the blood bank's local date.
    """
    latest = {}
    for donation_type, donation_date in donations:
        previous = latest.get(donation_type)
        if previous is None or donation_date > previous:
            latest[donation_type] = donation_date

    results = []
    for donation_type, min_interval_days in rules:
        last = latest.get(donation_type)
        if last is None:
            next_eligible = today
            eligible = True
        else:
            next_eligible = last + timedelta(days=min_interval_days)
            eligible = today >= next_eligible
        results.append(
            {
                "donation_type": donation_type,
                "min_interval_days": min_interval_days,
                "last_donation_date": last,
                "next_eligible_date": next_eligible,
                "eligible": eligible,
            }
        )
    return results
