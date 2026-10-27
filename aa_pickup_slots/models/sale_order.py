"""THE DAY AND THE WINDOW THE CUSTOMER PICKED, AND WHEN THEY MAY PICK IT.

Owner, 2026-10-27: *"At checkout, the customer picks a pickup day and time
window ... Our lead time is 2 labor days, after those 2 days they choose when
to pick up."*

THE LEAD TIME STARTS THE NEXT WORKING DAY. Asked which day an order placed on
Monday could first be collected, he chose Thursday: Tuesday and Wednesday are
the two labour days the work takes, and Thursday is the first day it can be
handed over. An order placed on Friday starts on Monday and is collectable on
Wednesday. The day the order is placed never counts, because an order placed
at ten to five has had none of it.

WEEKENDS AND CLOSED DAYS ARE NOT LABOUR DAYS, and are not offered either -
there is no point letting somebody book a Saturday when nobody is here. The
closed days are a setting, because a holiday is a date somebody has to type in
and no rule can know it.
"""

import json
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .pickup_time import is_a_pickup_time, pickup_times, time_label

#: Whole working days the shop needs before anything can be collected. Two,
#: and the day the order was placed is not one of them.
LEAD_DAYS = 2

#: How far ahead the customer may book.
OFFER_DAYS = 28

CLOSED_SETTING = "aa_pickup_slots.closed_days"


class SaleOrder(models.Model):
    _inherit = "sale.order"

    aa_pickup_date = fields.Date(
        string="Pickup Day", copy=False, index=True,
        help="The day the customer said they would collect this order.")
    aa_pickup_time = fields.Float(
        string="Pickup Time", copy=False, digits=(4, 2),
        help="The time of day the customer said they would come, in hours.")
    aa_pickup_label = fields.Char(
        string="Pickup", compute="_compute_aa_pickup_label", store=True,
        help="The day and window as one line, for the Work Order and Dispatch.")

    @api.depends("aa_pickup_date", "aa_pickup_time")
    def _compute_aa_pickup_label(self):
        for order in self:
            order.aa_pickup_label = order._aa_pickup_text()

    def _aa_pickup_text(self):
        """"Thu 30 Oct, 10:00 AM - 12:00 PM", or nothing at all.

        One string rather than two columns, because every place this has to
        appear - a printed sheet, a list somebody scans down - wants to read
        it in one go.
        """
        self.ensure_one()

        if not self.aa_pickup_date:
            return False

        day = self.aa_pickup_date.strftime("%a %-d %b")
        at = time_label(self.aa_pickup_time) if self.aa_pickup_time else ""

        return "%s, %s" % (day, at) if at else day

    # --- is this one being collected -------------------------------------

    def _aa_is_pickup(self):
        """Is this order being collected rather than delivered?

        Asked who should be made to choose a slot, the owner said pickup
        orders only - somebody having it delivered is never asked.
        """
        self.ensure_one()

        return bool(self.carrier_id and self.carrier_id.aa_is_pickup)

    # --- which days may be chosen ----------------------------------------

    @api.model
    def _aa_closed_days(self):
        """Dates the shop is shut, beyond the weekend. A setting, because a
        public holiday is something somebody types in."""
        raw = self.env["ir.config_parameter"].sudo().get_param(
            CLOSED_SETTING, "")
        closed = set()

        for piece in (raw or "").replace(";", ",").split(","):
            piece = piece.strip()

            if not piece:
                continue

            try:
                closed.add(fields.Date.to_date(piece))
            except (ValueError, TypeError):
                # A line somebody mistyped must not take the shop's checkout
                # down with it; the day simply stays open.
                continue

        return closed

    def _aa_is_working_day(self, day):
        return day.weekday() < 5 and day not in self._aa_closed_days()

    def _aa_earliest_pickup(self, placed=None):
        """The first day this order could be collected.

        Two WHOLE working days after the day it was placed, then the next
        working day after those. Monday -> Thursday; Friday -> Wednesday.
        """
        self.ensure_one()
        day = placed or fields.Date.context_today(self)
        worked = 0

        while worked < LEAD_DAYS:
            day += timedelta(days=1)

            if self._aa_is_working_day(day):
                worked += 1

        day += timedelta(days=1)

        while not self._aa_is_working_day(day):
            day += timedelta(days=1)

        return day

    def _aa_pickup_choices(self):
        """[(date, "Thursday 30 October")] for the checkout to offer."""
        self.ensure_one()
        first = self._aa_earliest_pickup()
        days = []
        day = first

        while len(days) < OFFER_DAYS and (day - first).days < OFFER_DAYS * 2:
            if self._aa_is_working_day(day):
                days.append((day, day.strftime("%A %-d %B")))

            day += timedelta(days=1)

        return days

    def _aa_pickup_time_choices(self):
        """[(7.0, "7:00 AM"), ...] across the hours the counter is open."""
        return pickup_times(self.env)

    def _aa_pickup_days_json(self):
        """The selectable days as a JSON list, for the calendar to read.

        The calendar is drawn in the browser and has to know which squares
        may be clicked. Sending the days rather than a rule keeps the two
        from ever disagreeing: a day the server would refuse is a day the
        calendar cannot offer.
        """
        self.ensure_one()

        return json.dumps(
            [day.isoformat() for day, _label in self._aa_pickup_choices()])

    # --- it cannot be paid for without one -------------------------------

    def _aa_pickup_problem(self):
        """Why this order may not be paid for yet, or nothing."""
        self.ensure_one()

        if not self._aa_is_pickup():
            return False

        if not self.aa_pickup_date or not self.aa_pickup_time:
            return _("Please choose the day and time you will collect this"
                     " order.")

        if not is_a_pickup_time(self.env, self.aa_pickup_time):
            return _("We are not open at that time. Please choose another.")

        allowed = [day for day, _label in self._aa_pickup_choices()]

        if self.aa_pickup_date not in allowed:
            # The page was open a long time, or somebody posted a date by
            # hand. Either way the day is no longer one we offer.
            return _("That pickup day is no longer available. Please choose"
                     " another.")

        return False

    def _check_cart_is_ready_to_be_paid(self):
        """Odoo's gate before payment, with the slot added to it.

        REQUIRED WAS HIS CHOICE (2026-10-27), and this is the only place that
        can hold it: the checkout page can be skipped, reloaded, or posted to
        directly, and a pickup order reaching Dispatch with no slot is
        somebody ringing the customer to ask.
        """
        result = super()._check_cart_is_ready_to_be_paid()
        problem = self._aa_pickup_problem()

        if problem:
            raise ValidationError(problem)

        return result

    # --- carried onto the order's paperwork ------------------------------

    def _action_confirm(self):
        """The slot goes with the order to the floor.

        Written onto the transfers at confirmation rather than read through a
        link, so the Dispatch list can sort and filter by it and the Work
        Order sheet prints without reaching back through the sale.
        """
        result = super()._action_confirm()

        for order in self:
            if order.aa_pickup_label and order.picking_ids:
                order.picking_ids.write({
                    "aa_pickup_date": order.aa_pickup_date,
                    "aa_pickup_time": order.aa_pickup_time,
                })

        return result
