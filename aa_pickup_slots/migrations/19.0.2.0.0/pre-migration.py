"""THE FOUR WINDOWS BECOME A TIME OF DAY.

Owner, 2026-10-27, having seen the first version: *"the customer should be
able to choose anytime between 7 and 4."* So `aa_pickup_slot` - a Selection
of four two-hour codes - is replaced by `aa_pickup_time`, an hour of the day.

Anything already booked under the old scheme is moved to the START of the
window it chose, which is the only honest reading: somebody who picked
"10:00 AM - 12:00 PM" was told to come at ten.

Written in SQL and in a PRE-migration because the new column does not exist
yet and the old one is about to stop being a field. Both tables, because the
transfer carries its own copy for the Dispatch list to sort on.
"""

import logging

_logger = logging.getLogger(__name__)

WINDOW_STARTS = {"08": 8.0, "10": 10.0, "12": 12.0, "14": 14.0}


def migrate(cr, version):
    for table in ("sale_order", "stock_picking"):
        cr.execute("""
            SELECT column_name FROM information_schema.columns
             WHERE table_name = %s AND column_name = 'aa_pickup_slot'
        """, (table,))

        if not cr.fetchone():
            continue

        cr.execute(
            "ALTER TABLE %s ADD COLUMN IF NOT EXISTS aa_pickup_time "
            "double precision" % table)

        for code, hour in WINDOW_STARTS.items():
            cr.execute(
                "UPDATE %s SET aa_pickup_time = %%s "
                " WHERE aa_pickup_slot = %%s AND aa_pickup_time IS NULL"
                % table, (hour, code))

        cr.execute("ALTER TABLE %s DROP COLUMN aa_pickup_slot" % table)
        _logger.info(
            "aa_pickup_slots: %s moved from pickup windows to a time of day",
            table)
