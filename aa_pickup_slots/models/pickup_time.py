"""THE TIMES THE COUNTER CAN BE COME TO, AND HOW THEY READ.

Owner, 2026-10-27, revising his earlier answer: *"the customer should be able
to choose anytime between 7 and 4, but dont make it a dropdown find some
other option to make it look good and let them choose a larger range of
time."*

So the two-hour windows are gone. The time is now a NUMBER OF HOURS - 7.0,
7.5, 16.0 - rather than one of four codes, which is what lets the range move
without the stored values meaning something different afterwards. Half-hour
steps across 7:00 to 4:00 is nineteen choices, which is a grid of buttons and
not a dropdown.

THE RANGE IS A SETTING. He has already changed it once, from 8:00-4:30 to
7:00-4:00, and a number that has moved once will move again.
"""

import logging
from datetime import datetime, time, timedelta

import pytz

_logger = logging.getLogger(__name__)

#: WHERE THE COUNTER IS, which until now this module never had to say.
#:
#: Every hour in here - the 7:00 to 4:00 he chose, the label on the Dispatch
#: list, the times offered at checkout - is SHOP LOCAL TIME, and nothing ever
#: converted because nothing ever left that world. Writing the slot onto
#: `scheduled_date` does leave it: that field is a naive UTC datetime, so
#: "1:30 PM" has to be told which 1:30 PM it is.
#:
#: Guessing it was not good enough. This database's own candidates are a
#: company calendar saying UTC (Odoo's default, not a statement about the
#: shop), a blank partner timezone, and whichever timezone the person
#: pressing the button happens to be in - a website customer could be
#: anywhere. So it is a setting, and its default is the fact already written
#: down: the shop works 7:00-4:00 Eastern.
TZ_SETTING = "aa_pickup_slots.timezone"
DEFAULT_TZ = "America/Toronto"

FROM_SETTING = "aa_pickup_slots.open_from"
TO_SETTING = "aa_pickup_slots.open_to"

#: His counter hours as of 2026-10-27. Overridden by the settings above.
DEFAULT_FROM = 7.0
DEFAULT_TO = 16.0

#: Half an hour. Fine enough to be a real appointment, coarse enough that
#: nineteen buttons still fit on a phone.
STEP = 0.5


def shop_timezone(env):
    """The counter's own timezone, or Eastern.

    A mistyped zone falls back rather than raising, the same call as the
    closed days: a transfer that cannot be saved over a fat-fingered setting
    is worse than one scheduled an hour out.
    """
    name = (env["ir.config_parameter"].sudo().get_param(TZ_SETTING)
            or "").strip()

    try:
        return pytz.timezone(name or DEFAULT_TZ)
    except pytz.UnknownTimeZoneError:
        _logger.warning("aa_pickup_slots: %r is not a timezone; using %s",
                        name, DEFAULT_TZ)

        return pytz.timezone(DEFAULT_TZ)


def slot_in_utc(env, day, hour):
    """A pickup day and hour-of-day as the naive UTC datetime Odoo stores.

    DST IS THE WHOLE REASON THIS IS NOT ARITHMETIC. 1:30 PM on a day in July
    and 1:30 PM on a day in November are an hour apart in UTC, and the shop
    says 1:30 PM both times.
    """
    if not day:
        return False

    if not hour:
        # A day with no time - a back-office order, since a customer cannot
        # pay without choosing one. Taken as the counter opening, which is
        # the earliest they could be there.
        hour = opening_hours(env)[0]

    hours = int(hour)
    minutes = int(round((hour - hours) * 60))
    local = datetime.combine(day, time()) + timedelta(hours=hours,
                                                      minutes=minutes)

    return shop_timezone(env).localize(local).astimezone(
        pytz.UTC).replace(tzinfo=None)


def _as_float(raw, fallback):
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return fallback

    return value if 0.0 <= value <= 24.0 else fallback


def opening_hours(env):
    """(from, to) in hours, from the settings, always the right way round."""
    config = env["ir.config_parameter"].sudo()
    start = _as_float(config.get_param(FROM_SETTING), DEFAULT_FROM)
    end = _as_float(config.get_param(TO_SETTING), DEFAULT_TO)

    if end <= start:
        # Somebody typed them backwards, or the same. Rather than offer a
        # customer nothing at all, fall back to the hours we shipped with.
        return DEFAULT_FROM, DEFAULT_TO

    return start, end


def pickup_times(env):
    """[(7.0, "7:00 AM"), (7.5, "7:30 AM"), ...] across the open hours."""
    start, end = opening_hours(env)
    times = []
    at = start

    while at <= end + 1e-9:
        times.append((round(at, 2), time_label(at)))
        at += STEP

    return times


def time_label(value):
    """7.5 -> "7:30 AM"; 16.0 -> "4:00 PM"; 12.0 -> "12:00 PM"."""
    if not value and value != 0:
        return ""

    hours = int(value)
    minutes = int(round((value - hours) * 60))

    if minutes == 60:
        hours, minutes = hours + 1, 0

    suffix = "AM" if hours < 12 else "PM"
    shown = hours % 12 or 12

    return "%d:%02d %s" % (shown, minutes, suffix)


def is_a_pickup_time(env, value):
    """Is this one of the times actually on offer?

    Compared on the label rather than on the float, because a half hour is
    not exactly representable and 7.5 arriving as 7.499999 should still be
    half past seven.
    """
    if not value:
        return False

    return any(abs(value - offered) < 1e-6 for offered, _label
               in pickup_times(env))
