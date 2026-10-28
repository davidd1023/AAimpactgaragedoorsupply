"""HOW LONG THE COIL WILL LAST AT THE PACE OF RECENT ORDERS.

Owner, 2026-10-28: *"Spring Engineering already knows the inches every order
cuts. I want it to track the spring wire size and id inventory and send a
warning somewhere that at the current pace of orders being made we will likely
run out of material in x amount of days."*

Nothing new is measured: `aa.spring.cut` has logged every spring ever cut -
dated, with its wire, its I.D. and its inches - and the quants hold what is
left. The whole feature is one division, and every test below is about what
the two numbers going into it MEAN.

Asked where to show it he chose the stock screens and no email, and fourteen
days as the line.
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from .test_coil_consumption import CoilStockMixin


@tagged("post_install", "-at_install")
class SpringRunoutCase(CoilStockMixin, TransactionCase):

    WINDOW = 30

    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param(
            "aa_spring_stock.pace_days", str(self.WINDOW))
        self.env["ir.config_parameter"].sudo().set_param(
            "aa_spring_stock.runout_warn_days", "14")

    # --- helpers --------------------------------------------------------------

    def cut(self, hand, inches, days_ago=1, state="done"):
        """One entry in the cut history, as a finished Springs job leaves it."""
        return self.env["aa.spring.cut"].create({
            "date": fields.Datetime.now() - timedelta(days=days_ago),
            "hand": hand,
            "wire": "262",
            "inside_diameter": '2 5/8"',
            "product_id": self.coil[hand].id,
            "length": inches,
            "state": state,
        })

    def row(self):
        """The Spring Inventory line for the 2 5/8" .262 coil."""
        # RAW SQL BEHIND IT, so the ORM's pending writes have to be on disk
        # first - the add-on counter cost a whole run learning that.
        self.env.flush_all()
        self.env["aa.spring.stock.summary"].invalidate_model()
        rows = self.env["aa.spring.stock.summary"].search(
            [("wire", "=", "262"), ("inside_diameter_num", "=", 2.625)])

        self.assertEqual(len(rows), 1, "expected exactly one row for this coil")

        return rows

    # --- the sentence he wrote ------------------------------------------------

    def test_days_left_is_the_free_inches_over_the_daily_pace(self):
        """THE ONE THAT SETTLES IT. 600" on hand, 300" cut over 30 days, so
        10" a day and sixty days left."""
        self.put("L", "L-1", self.floor, 600.0)
        self.put("R", "R-1", self.floor, 600.0)
        self.cut("L", 300.0)
        self.cut("R", 300.0)

        row = self.row()

        self.assertAlmostEqual(row.used_per_day_in, 20.0, 2,
                               "both hands together: 300+300 over 30 days")
        self.assertAlmostEqual(row.days_left, 60.0, 0)
        self.assertEqual(row.runout, "ok")
        self.assertEqual(row.cuts_counted, 2)

    def test_the_worse_hand_decides(self):
        """A spring takes a LH piece AND a RH piece, so a mountain of LH with
        no RH has run out - the same reasoning as the pairs alert."""
        self.put("L", "L-1", self.floor, 6000.0)
        self.put("R", "R-1", self.floor, 300.0)
        self.cut("L", 300.0)
        self.cut("R", 300.0)

        row = self.row()

        # LH alone would be 600 days. RH is 30.
        self.assertAlmostEqual(row.days_left, 30.0, 0,
                               "the hand that runs out first has to win")

    def test_a_hand_nobody_orders_does_not_drag_it_to_zero(self):
        """The other half of that: a hand with no demand cannot run out, so it
        drops OUT of the comparison rather than reading as nothing left. This
        is what `LEAST` ignoring nulls buys."""
        self.put("L", "L-1", self.floor, 300.0)
        self.put("R", "R-1", self.floor, 300.0)
        self.cut("L", 300.0)

        row = self.row()

        self.assertAlmostEqual(row.days_left, 30.0, 0,
                               "RH has no pace, so LH decides")

    # --- no pace means no answer ---------------------------------------------

    def test_a_size_nobody_has_cut_shows_no_figure_at_all(self):
        """NOT A WARNING AND NOT "FOREVER". He asked what happens at the
        CURRENT pace; where there is no pace there is nothing to say, and a
        warning on a size that never moves is the noise that would cost the
        real ones their credibility."""
        self.put("L", "L-1", self.floor, 84.0)
        self.put("R", "R-1", self.floor, 84.0)

        row = self.row()

        self.assertFalse(row.days_left)
        self.assertEqual(row.runout, "none")
        self.assertFalse(row.used_per_day_in)

    def test_a_cut_older_than_the_window_is_not_the_current_pace(self):
        self.put("L", "L-1", self.floor, 300.0)
        self.put("R", "R-1", self.floor, 300.0)
        self.cut("L", 300.0, days_ago=self.WINDOW + 5)
        self.cut("R", 300.0, days_ago=self.WINDOW + 5)

        row = self.row()

        self.assertEqual(row.runout, "none",
                         "last month's orders are not the current pace")

    def test_the_window_is_a_setting(self):
        """Widen it and the old cut counts again - which is the point of its
        being a setting: one big dealer order in a short window makes the shop
        look like it is running out."""
        self.put("L", "L-1", self.floor, 300.0)
        self.put("R", "R-1", self.floor, 300.0)
        self.cut("L", 300.0, days_ago=40)
        self.cut("R", 300.0, days_ago=40)
        self.assertEqual(self.row().runout, "none")

        self.env["ir.config_parameter"].sudo().set_param(
            "aa_spring_stock.pace_days", "90")

        self.assertAlmostEqual(self.row().days_left, 90.0, 0)

    # --- what counts as on hand ----------------------------------------------

    def test_inches_a_confirmed_order_has_reserved_are_not_free(self):
        """FREE INCHES, NOT INCHES. Confirming a Springs order reserves the
        piece each spring is cut from, so those inches are spoken for -
        counting them would promise material that is already claimed."""
        self.put("L", "L-1", self.floor, 300.0)
        self.put("R", "R-1", self.floor, 300.0)
        self.cut("L", 300.0)
        self.cut("R", 300.0)
        before = self.row().days_left

        # A real order, which reserves 60" of each hand.
        self.make_order(length=60.0, springs=2)

        after = self.row()

        self.assertLess(after.days_left, before,
                        "a reserved piece still counted as free")
        self.assertAlmostEqual(after.free_l_in, 240.0, 1)

    # --- demand that could not be served -------------------------------------

    def test_an_order_with_no_piece_long_enough_still_counts_as_demand(self):
        """A `short` cut is an order that WANTED this size and found nothing
        long enough. Leaving it out would understate the pace at exactly the
        moment stock is tightest, which is the worst time to be optimistic."""
        self.put("L", "L-1", self.floor, 300.0)
        self.put("R", "R-1", self.floor, 300.0)
        self.cut("L", 300.0, state="short")
        self.cut("R", 300.0, state="short")

        row = self.row()

        self.assertAlmostEqual(row.days_left, 30.0, 0)

    def test_a_cut_that_is_only_planned_is_not_consumption_yet(self):
        """It has not been cut - and its inches are already off the free
        figure through the reservation, so counting it here as well would take
        it off twice."""
        self.put("L", "L-1", self.floor, 300.0)
        self.put("R", "R-1", self.floor, 300.0)
        self.cut("L", 300.0, state="planned")
        self.cut("R", 300.0, state="planned")

        self.assertEqual(self.row().runout, "none")

    # --- the warning itself ---------------------------------------------------

    def test_under_the_threshold_it_says_running_out(self):
        self.put("L", "L-1", self.floor, 100.0)
        self.put("R", "R-1", self.floor, 100.0)
        self.cut("L", 300.0)
        self.cut("R", 300.0)

        row = self.row()

        self.assertAlmostEqual(row.days_left, 10.0, 0)
        self.assertEqual(row.runout, "soon")

    def test_the_threshold_is_a_setting(self):
        """He chose fourteen days when asked - about what a steel order takes
        to arrive. That is his supplier's lead time, which changes."""
        self.put("L", "L-1", self.floor, 600.0)
        self.put("R", "R-1", self.floor, 600.0)
        self.cut("L", 300.0)
        self.cut("R", 300.0)
        self.assertEqual(self.row().runout, "ok", "sixty days is not low")

        self.env["ir.config_parameter"].sudo().set_param(
            "aa_spring_stock.runout_warn_days", "90")

        self.assertEqual(self.row().runout, "soon")

    def test_demand_with_nothing_left_is_out_of_material(self):
        """The worst case, and it has to read differently from merely low."""
        self.put("L", "L-1", self.floor, 300.0)
        self.cut("L", 300.0)
        self.cut("R", 300.0)

        row = self.row()

        self.assertEqual(row.runout, "now")
        self.assertAlmostEqual(row.days_left, 0.0, 1)

    # --- it must not be able to take the screen down -------------------------

    def test_a_mistyped_setting_falls_back_instead_of_raising(self):
        """A screen that 500s over a fat-fingered number is worse than one
        quietly using the default - the same call as the pickup holidays."""
        self.put("L", "L-1", self.floor, 300.0)
        self.put("R", "R-1", self.floor, 300.0)
        self.cut("L", 300.0)
        self.cut("R", 300.0)

        for bad in ("", "abc", "-5", "14.5", "0"):
            self.env["ir.config_parameter"].sudo().set_param(
                "aa_spring_stock.pace_days", bad)

            self.assertAlmostEqual(
                self.row().days_left, 30.0, 0,
                "pace_days=%r should have fallen back to 30" % bad)

    def test_the_pairs_alert_is_untouched(self):
        """It answers a different question - "is there a coil behind this
        one" - and the two disagree usefully. Nothing here may change it."""
        self.put("L", "L-1", self.floor, 84.0)
        self.put("R", "R-1", self.floor, 84.0)
        self.cut("L", 300.0)
        self.cut("R", 300.0)

        row = self.row()

        self.assertEqual(row.alert, "order", "one pair, no box behind it")
        self.assertEqual(row.runout, "soon", "and under a fortnight of it")

    # --- the bug this feature uncovered --------------------------------------

    def test_an_order_reserves_its_inches_once(self):
        """FOUND BY BUILDING THE RUN-OUT FIGURE, 2026-10-28.

        Raising a confirmed move's demand makes Odoo reserve it immediately,
        off whichever quant it likes - and the deliberate line was then added
        ON TOP, so a 60" spring stood 120" reserved against a 60" demand.

        It never lost material: the right inches come off at `done`, which the
        consumption tests already prove. What it did was HIDE GOOD COIL.
        `_aa_coil_pieces` offers `quantity - reserved_quantity`, so a piece
        with plenty left looked too short - pushing the next order onto the
        Floor, then the Boxes, and eventually logging "No piece is long
        enough" with a full coil sitting on the rack.
        """
        self.put("L", "L-1", self.floor, 300.0)
        self.put("R", "R-1", self.floor, 300.0)

        self.make_order(length=60.0, springs=2)

        for hand in ("L", "R"):
            quants = self.env["stock.quant"].search([
                ("product_id", "=", self.coil[hand].id),
                ("location_id.usage", "=", "internal")])

            self.assertAlmostEqual(
                sum(quants.mapped("reserved_quantity")), 60.0, 2,
                "%s hand reserved more than the spring takes" % hand)

    def test_the_reservation_is_on_the_piece_this_code_chose(self):
        """Odoo's own guess at the lot is REPLACED, not added to - otherwise
        the shop floor is told to cut one piece while another is reserved."""
        self.put("L", "L-short", self.rack, 70.0)
        self.put("L", "L-long", self.floor, 300.0)
        self.put("R", "R-1", self.floor, 300.0)

        production = self.make_order(length=60.0, springs=1)
        planned = production.aa_spring_cut_ids.filtered(lambda c: c.hand == "L")

        self.assertEqual(planned.lot_id.name, "L-short",
                         "the rack piece that fits should have been chosen")

        lines = production.move_raw_ids.filtered(
            lambda m: m.product_id == self.coil["L"]).move_line_ids

        self.assertEqual(lines.lot_id.mapped("name"), ["L-short"],
                         "reserved a different piece from the one to cut")
