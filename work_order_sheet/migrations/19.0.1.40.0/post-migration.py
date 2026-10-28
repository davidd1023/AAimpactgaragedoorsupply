"""EVERY ORDER ALREADY CANCELLED COUNTS AS ALREADY TOLD.

The cancellation email now goes out when the last manufacturing job for an
order is cancelled, which is a trigger that did not exist before this version.
His database has orders cancelled weeks ago whose jobs are still standing open
on the floor - the Shop-floor cleanup screen exists precisely to close them -
and the first person to use that screen after this deploys would otherwise
email a dozen customers that an order they cancelled in September is
cancelled.

So every order that is ALREADY cancelled is stamped here. They were told at
the time or they were not, and either way it is far too late for this to be
news. Only cancellations from here on send.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE sale_order
           SET aa_cancel_email_sent = now() AT TIME ZONE 'UTC'
         WHERE state = 'cancel'
           AND aa_cancel_email_sent IS NULL
    """)
