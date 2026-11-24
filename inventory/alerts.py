
from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from .choices import BloodType, Component
from .models import BloodUnit, ShelfLifeRule, StockThreshold


def save_threshold(*, blood_type, component, minimum_units, coordinator, **extra):

    defaults = {"minimum_units": minimum_units, "updated_by": coordinator}
    if "expiring_soon_days" in extra:
        defaults["expiring_soon_days"] = extra["expiring_soon_days"]
    return StockThreshold.objects.update_or_create(
        blood_type=blood_type, component=component, defaults=defaults
    )


def _unit_row(unit, window_days):
    return {
        "id": unit["id"],
        "unit_code": unit["unit_code"],
        "blood_type": unit["blood_type"],
        "component": unit["component"],
        "expires_at": unit["expires_at"],
        "window_days": window_days,
    }


def build_dashboard(now=None):
    now = now or timezone.now()
    default_window = {
        rule.component: rule.expiring_soon_days for rule in ShelfLifeRule.objects.all()
    }
    thresholds = {(t.blood_type, t.component): t for t in StockThreshold.objects.all()}

    usable = defaultdict(list)
    for unit in BloodUnit.objects.usable().order_by("expires_at", "id").values(
        "id", "unit_code", "blood_type", "component", "expires_at"
    ):
        usable[(unit["blood_type"], unit["component"])].append(unit)

    stock, low_stock = [], []
    expiring = {component: [] for component in Component.values}
    for component in Component.values:
        for blood_type in BloodType.values:
            threshold = thresholds.get((blood_type, component))
            window = (
                threshold.expiring_soon_days
                if threshold and threshold.expiring_soon_days
                else default_window.get(component)
            )
            units = usable[(blood_type, component)]
            closest = units[0] if units else None
            is_low = threshold is not None and len(units) < threshold.minimum_units
            stock.append(
                {
                    "blood_type": blood_type,
                    "component": component,
                    "available": len(units),
                    "minimum_units": threshold.minimum_units if threshold else None,
                    "expiring_soon_days": window,
                    "is_low": is_low,
                    "closest_to_expiry": _unit_row(closest, window) if closest else None,
                }
            )
            if is_low:
                low_stock.append(
                    {
                        "blood_type": blood_type,
                        "component": component,
                        "available": len(units),
                        "minimum_units": threshold.minimum_units,
                    }
                )
            if window:
                cutoff = now + timedelta(days=window)
                # Units are sorted by expiry, so stop at the first one outside the window.
                for unit in units:
                    if unit["expires_at"] > cutoff:
                        break
                    expiring[component].append(_unit_row(unit, window))

    expiring_soon = [
        {
            "component": component,
            "label": label,
            "window_days": default_window.get(component),
            "units": sorted(expiring[component], key=lambda u: (u["expires_at"], u["id"])),
        }
        for component, label in Component.choices
    ]
    return {
        "generated_at": now,
        "low_stock": low_stock,
        "expiring_soon": expiring_soon,
        "stock": stock,
    }
