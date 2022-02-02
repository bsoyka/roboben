"""Time-related utilities."""

from typing import Literal

from dateutil.relativedelta import relativedelta

_Precision = Literal["years", "months", "days", "hours", "minutes", "seconds"]


def _stringify_time_unit(value: int, unit: str) -> str:
    """
    Return a string to represent a value and time unit, ensuring the unit's correct plural form is used.
    >>> _stringify_time_unit(1, "seconds")
    "1 second"
    >>> _stringify_time_unit(24, "hours")
    "24 hours"
    >>> _stringify_time_unit(0, "minutes")
    "less than a minute"
    """
    if unit == "seconds" and value == 0:
        return "0 seconds"
    if value == 1:
        return f"1 {unit[:-1]}"
    if value == 0:
        return f"less than a {unit[:-1]}"

    return f"{value} {unit}"


def humanize_delta(
    delta: relativedelta,
    precision: _Precision = "seconds",
    max_units: int = 6,
) -> str:
    """Returns a human-readable version of a `relativedelta`.

    `precision` is the smallest unit of time to include (e.g. "seconds", "minutes").
    `max_units` is the maximum number of units of time to include.
    """
    if max_units <= 0:
        raise ValueError("max_units must be positive.")

    units = (
        ("years", delta.years),
        ("months", delta.months),
        ("days", delta.days),
        ("hours", delta.hours),
        ("minutes", delta.minutes),
        ("seconds", delta.seconds),
    )

    # Add the time units that are >0, but stop at precision or max_units.
    time_strings = []
    unit_count = 0
    for unit, value in units:
        if value:
            time_strings.append(_stringify_time_unit(value, unit))
            unit_count += 1

        if unit == precision or unit_count >= max_units:
            break

    # Add the 'and' between the last two units, if necessary.
    if len(time_strings) > 1:
        time_strings[-1] = f"{time_strings[-2]} and {time_strings[-1]}"
        del time_strings[-2]

    # If nothing has been found, just make the value 0 precision, e.g. `0 days`.
    return _stringify_time_unit(0, precision) if not time_strings else ", ".join(time_strings)
