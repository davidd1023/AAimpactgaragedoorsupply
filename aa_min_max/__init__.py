from . import models

from .models.minmax_load import load_levels_once


def post_init_hook(env):
    """Load his filled-in minimums the first time this is installed.

    THE NUMBERS ARE HIS WORK, not a default - 157 of them, worked out from 180
    doors of cover. Shipping them and making him press a button to get them in
    would be asking him to do the last step of a job he already did in a
    spreadsheet.

    Re-runnable from the screen afterwards (the "Load Levels From File"
    button), which is the lesson of the catalogue merge: a migration runs once
    and only on a version bump, so a screen is the only way back in.
    """
    load_levels_once(env)
