"""TICK THE PICKUP METHODS ONCE, so the thing works the day it is installed.

A fresh flag defaulting to False would mean no order is ever a pickup order
and the checkout never asks anybody anything - which looks exactly like the
feature not working. So anything that already reads as a collection method is
ticked here, and after that the box is his.
"""

import logging

_logger = logging.getLogger(__name__)


def _aa_mark_pickup_carriers(env):
    carriers = env["delivery.carrier"].sudo().search([])
    pickups = carriers.filtered(
        lambda carrier: carrier.delivery_type == "in_store"
        or "pickup" in (carrier.name or "").lower()
        or "pick up" in (carrier.name or "").lower()
        or "collect" in (carrier.name or "").lower()
    )

    if pickups:
        pickups.write({"aa_is_pickup": True})

    _logger.info(
        "aa_pickup_slots: %d of %d delivery methods marked as collected in "
        "person: %s", len(pickups), len(carriers),
        ", ".join(pickups.mapped("name")) or "none")
