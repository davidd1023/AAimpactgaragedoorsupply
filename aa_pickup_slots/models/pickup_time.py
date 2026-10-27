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

FROM_SETTING = "aa_pickup_slots.open_from"
TO_SETTING = "aa_pickup_slots.open_to"

#: His counter hours as of 2026-10-27. Overridden by the settings above.
DEFAULT_FROM = 7.0
DEFAULT_TO = 16.0

#: Half an hour. Fine enough to be a real appointment, coarse enough that
#: nineteen buttons still fit on a phone.
STEP = 0.5


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
