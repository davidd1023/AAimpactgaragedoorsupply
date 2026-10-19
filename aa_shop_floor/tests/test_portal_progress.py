"""WHERE THE CUSTOMER'S ORDER HAS GOT TO, on the customer's own pages.

The owner, 2026-10-19: in My Account > Your Orders the customer should be able
to see that the tracks are finished, the springs are being worked on and the
hardware has not started yet - instead of only Odoo's Not Delivered.
"""

from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class PortalProgressCase(HttpCase):

    PASSWORD = "aa-customer-password"

    def setUp(self):
        super().setUp()
        self.customer = self.env["res.users"].create({
            "name": "A Customer",
            "login": "aa_customer",
            "password": self.PASSWORD,
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
        })
        self.product = self.env["product.product"].create({
            "name": "A thing", "type": "consu", "is_storable": True,
            "list_price": 10.0})
        self.stations = {
            name: self.env["mrp.workcenter"].search(
                [("name", "=ilike", name)], limit=1)
            or self.env["mrp.workcenter"].create({"name": name})
            for name in ("Springs", "Tracks", "Hardware")
        }

    def _order(self):
        order = self.env["sale.order"].create({
            "partner_id": self.customer.partner_id.id,
            "order_line": [(0, 0, {"product_id": self.product.id,
                                   "product_uom_qty": 1})],
        })
        order.action_confirm()

        return order

    def _job(self, order, station, state="ready", pending=False, worker=None):
        """A job of this order at a station, in the given state.

        `pending` puts it where a new job really waits - the Pending
        Assignment work center - while remembering the station it belongs to,
        which is what the manager's Send to station reads.
        """
        product = self.env["product.product"].create({
            "name": "Part for %s" % station, "type": "consu",
            "is_storable": True})
        production = self.env["mrp.production"].create({
            "product_id": product.id, "product_qty": 1.0, "origin": order.name})
        workcenter = self.stations[station]
        values = {
            "name": "Make it",
            "production_id": production.id,
            "product_uom_id": production.product_uom_id.id,
            "workcenter_id": workcenter.id,
            "state": state,
        }

        if pending:
            waiting = self.env["mrp.workcenter"].sudo()._aa_pending()
            values["workcenter_id"] = waiting.id
            values["aa_suggested_workcenter_id"] = workcenter.id

        workorder = self.env["mrp.workorder"].with_context(
            aa_keep_workcenter=True).create(values)

        if worker:
            workorder.employee_ids = [(6, 0, worker.ids)]

        if state == "done":
            production.state = "done"

        return production

    def _progress(self, order):
        return {row["label"]: row["words"]
                for row in order._aa_station_progress()}

    # --- what the customer is told -------------------------------------------

    def test_each_station_says_where_it_has_got_to(self):
        """The owner's own example: tracks finished, springs being worked on,
        hardware not started."""
        order = self._order()
        self._job(order, "Tracks", state="done")
        self._job(order, "Springs", state="progress")
        self._job(order, "Hardware", pending=True)

        self.assertEqual(self._progress(order), {
            "Tracks": "Finished",
            "Springs": "Being made",
            "Hardware": "Not started",
        })

    def test_an_order_nobody_is_making_says_nothing(self):
        """Parts off the shelf are not made at a bench, and a heading with no
        stations under it would leave somebody wondering what is missing."""
        order = self._order()
        self.assertEqual(order._aa_station_progress(), [])
        self.assertEqual(order._aa_progress_summary(), "")

    def test_waiting_and_queued_read_the_same_to_a_customer(self):
        """FOUR STATES INSIDE, THREE OUTSIDE. Whether a job has been sent to
        its bench or is still waiting to be sent is the manager's business;
        to the customer both are "not started"."""
        queued = self._order()
        self._job(queued, "Springs", state="ready")
        waiting = self._order()
        self._job(waiting, "Springs", pending=True)

        self.assertEqual(self._progress(queued), {"Springs": "Not started"})
        self.assertEqual(self._progress(waiting), {"Springs": "Not started"})

    def test_a_station_is_finished_only_when_all_of_it_is(self):
        """Two springs on one order: one wound, one not. The station is not
        finished, and saying so would have the customer expecting it."""
        order = self._order()
        self._job(order, "Springs", state="done")
        self._job(order, "Springs", state="progress")
        self.assertEqual(self._progress(order), {"Springs": "Being made"})

    def test_the_stations_come_in_the_order_the_shop_works_in(self):
        """A list that reorders itself between two visits looks broken."""
        order = self._order()
        self._job(order, "Hardware", state="done")
        self._job(order, "Tracks", state="done")
        self._job(order, "Springs", state="done")
        self.assertEqual([row["label"] for row in order._aa_station_progress()],
                         ["Springs", "Tracks", "Hardware"])

    def test_the_summary_counts_what_is_ready(self):
        order = self._order()
        self._job(order, "Springs", state="done")
        self._job(order, "Tracks", state="done")
        self._job(order, "Hardware", state="progress")
        self.assertEqual(order._aa_progress_summary(), "2 of 3 ready")

    def test_the_warehouse_and_the_customer_are_told_the_same_thing(self):
        """ONE COMPUTATION. The transfer's own Order Status has shown this
        since the 14th; the customer's page reads the same reckoning rather
        than a second opinion that can drift."""
        order = self._order()
        self._job(order, "Springs", state="progress")
        self._job(order, "Tracks", state="done")
        picking = self.env["stock.picking"].search(
            [("origin", "=", order.name)], limit=1)
        self.assertTrue(picking, "confirming the order made no transfer")
        self.assertEqual(
            dict(picking._aa_station_statuses()),
            {"Springs": "progress", "Tracks": "done"})

    # --- on the pages themselves ---------------------------------------------

    def test_the_orders_page_shows_it(self):
        order = self._order()
        self._job(order, "Springs", state="progress")
        self._job(order, "Tracks", state="done")
        self.authenticate("aa_customer", self.PASSWORD)
        page = self.url_open("/my/orders").text

        self.assertIn("Progress", page, "the column is not there")
        self.assertIn("Springs", page)
        self.assertIn("Being made", page)
        self.assertIn("Tracks", page)
        self.assertIn("Finished", page)

    def test_the_order_s_own_page_shows_it(self):
        order = self._order()
        self._job(order, "Hardware", pending=True)
        self.authenticate("aa_customer", self.PASSWORD)
        page = self.url_open("/my/orders/%d" % order.id).text

        self.assertIn("How your order is being made", page)
        self.assertIn("Hardware", page)
        self.assertIn("Not started", page)

    def test_the_customer_is_told_nothing_about_the_shop(self):
        """A PORTAL PAGE IS PUBLIC TO ANYBODY WITH THE LINK. Who is making it,
        how long it took and how long it sat in a queue are the shop's
        business - they belong to the Shop Floor history, not here."""
        worker = self.env["hr.employee"].create({"name": "Michel the Winder"})
        order = self._order()
        self._job(order, "Springs", state="progress", worker=worker)
        self.authenticate("aa_customer", self.PASSWORD)

        for url in ("/my/orders", "/my/orders/%d" % order.id):
            page = self.url_open(url).text
            self.assertNotIn("Michel the Winder", page, url)
            self.assertNotIn("start to finish", page, url)
            self.assertNotIn("Pending Assignment", page, url)

    def test_the_manufacturing_order_numbers_are_gone(self):
        """AAM/MO/00054 is internal numbering a customer cannot act on, and it
        answered the same question as the station list in the shop's own
        language. Two answers to one question is worse than one."""
        order = self._order()
        production = self._job(order, "Springs", state="progress")
        self.authenticate("aa_customer", self.PASSWORD)
        page = self.url_open("/my/orders/%d" % order.id).text

        self.assertNotIn(production.name, page, "the MO number is still shown")
        self.assertNotIn("Manufacturing Orders", page)
        self.assertIn("How your order is being made", page)

    def test_a_finished_station_says_when(self):
        """The one thing worth keeping from the numbers: the day it was
        done."""
        order = self._order()
        production = self._job(order, "Tracks", state="done")
        production.date_finished = "2026-10-19 12:00:00"
        rows = {row["label"]: row["date"] for row in order._aa_station_progress()}
        self.assertTrue(rows["Tracks"], "no date on a finished station")

    def test_an_unfinished_station_claims_no_date(self):
        order = self._order()
        self._job(order, "Springs", state="progress")
        rows = {row["label"]: row["date"] for row in order._aa_station_progress()}
        self.assertEqual(rows["Springs"], "")

    def test_another_customer_s_order_is_not_shown(self):
        """The progress is read off the order, so it is only ever as visible
        as the order is - but that is worth holding down."""
        mine = self._order()
        self._job(mine, "Springs", state="progress")
        other = self.env["res.users"].create({
            "name": "Somebody else", "login": "aa_other",
            "password": self.PASSWORD,
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])]})
        self.authenticate("aa_other", self.PASSWORD)

        self.assertNotIn(mine.name, self.url_open("/my/orders").text)

        # NOT 403: Odoo sends somebody who asks for an order that is not
        # theirs back to their own account page, so what has to be held down
        # is that the order's progress does not travel with them.
        page = self.url_open("/my/orders/%d" % mine.id).text
        self.assertNotIn("How your order is being made", page)
        self.assertNotIn(mine.name, page)
