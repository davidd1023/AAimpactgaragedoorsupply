from odoo import SUPERUSER_ID, api

# The name the station shipped with, and the one the owner asked for.
SHIPPED = "Dispatch"
WANTED = "Hardware"


def migrate(cr, version):
    """Rename the last bench from Dispatch to Hardware.

    THE RECORD CANNOT BE UPDATED FROM THE DATA FILE. It is loaded noupdate, on
    purpose: these are the owner's records from the moment they exist, and a
    bench renamed on the live site must not be put back by the next module
    update. So the rename is done here instead - once, and only while the
    station still carries the name it shipped with, so a site that has already
    called it something else keeps its own word for it.

    THROUGH THE ORM RATHER THAN SQL, because the name is translatable and
    therefore a jsonb column: an UPDATE with a plain string would write a type
    the field cannot read back.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    station = env["work.station"].with_context(active_test=False).search(
        [("code", "=", "dispatch")], limit=1)

    if station and station.name == SHIPPED:
        station.name = WANTED
