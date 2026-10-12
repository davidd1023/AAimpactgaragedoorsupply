import html
import json
import re

from odoo.exceptions import UserError
from odoo.tests.common import HttpCase, TransactionCase, tagged


def spec(**overrides):
    """A door as the calculator sends it: 9' x 7', 3" 15R, standard lift."""
    base = {
        "wo": "W-1001", "mark": "A",
        "width": 108, "height": 84,
        "track": "3-15R", "lift": "standard", "hilift": 0,
        "weight": 300, "sections": 4,
        "vertical": 76, "horizontal": 96,
        "cable": 123, "cable_type": 'Cable 5/32"', "drum": "D400-144",
        # what the two info papers print
        "projection": 6.5, "config": "3in 15R - Standard Lift",
        "jb": {"j10": 4, "j12": 4, "j14": 4, "j16": None},
        "ebf": "EBP 3 3/8in", "capacity": 375, "ftsc": 85.125,
    }
    base.update(overrides)

    return json.dumps(base)


class DoorWorkOrderCommon(TransactionCase):
    def setUp(self):
        super().setUp()
        self.params = self.env["ir.config_parameter"].sudo()
        self.track_3 = self.env["product.product"].create({
            "name": '3" Track Stock 20ft', "type": "consu"})
        self.track_2 = self.env["product.product"].create({
            "name": '2" Track Stock 20ft', "type": "consu"})
        self.params.set_param(
            "door_work_order.track_3_product_id", str(self.track_3.id))
        self.params.set_param(
            "door_work_order.track_2_product_id", str(self.track_2.id))
        self.Production = self.env["mrp.production"]

    def _items(self, production):
        return {i.role: i for i in production.door_wo_item_ids}

    def _reel(self, name):
        """The catalogue's reel if it has one, otherwise a stand-in.

        REUSED, NEVER DUPLICATED. A test that creates its own
        "5/32\" 7x19 Cable 500ft Reel" beside the real one asserts against its
        copy while the lookup quite correctly returns the original, and the
        assertion fails for a reason that has nothing to do with the code. That
        mistake has now been made three times in this repository - twice on the
        jamb brackets and once here - which is why it is a helper rather than a
        line repeated in each test.
        """
        found = self.env["product.product"].search(
            [("name", "=ilike", name)], limit=1)

        if found:
            return found

        return self.env["product.product"].create({"name": name, "type": "consu"})


@tagged("post_install", "-at_install")
class TestDoorWorkOrder(DoorWorkOrderCommon):
    """One door in, one manufacturing order out, carrying the cut list."""

    def test_a_door_becomes_one_order_with_three_cuts(self):
        production, reused = self.Production._door_wo_create(spec())
        self.assertFalse(reused)
        items = self._items(production)
        self.assertEqual(
            set(items), {"track_vertical", "track_horizontal", "cable"})
        self.assertEqual(items["track_vertical"].length_inches, 76)
        self.assertEqual(items["track_horizontal"].length_inches, 96)
        self.assertEqual(items["cable"].length_inches, 123)
        # TWO OF EVERYTHING, because a door has two sides. This is the figure
        # the tracks feature got wrong twice by reading a per-side number as a
        # per-door one, so it is asserted rather than assumed.
        for item in items.values():
            self.assertEqual(item.quantity, 2, item.role)

    def test_the_tracks_are_cut_from_the_stock_for_their_size(self):
        production, _r = self.Production._door_wo_create(spec(track="3-15R"))
        self.assertEqual(
            self._items(production)["track_vertical"].product_id, self.track_3)

        production, _r = self.Production._door_wo_create(
            spec(wo="W-1002", track="2-12R"))
        self.assertEqual(
            self._items(production)["track_vertical"].product_id, self.track_2)

    def test_the_cable_reel_is_matched_by_size(self):
        """5/32" must not be cut from the 1/8" reel.

        The calculator picks the cable from the drum - its CTYPE table - so the
        size arriving here is already decided, and the only question is which
        reel it comes off. Matched by name as a default because the live
        catalogue cannot be read from a development build.
        """
        reel = self._reel('5/32" 7x19 Cable 500ft Reel')
        decoy = self._reel('1/8" 7x19 Cable 500ft Reel')
        production, _r = self.Production._door_wo_create(spec())
        self.assertEqual(self._items(production)["cable"].product_id, reel)
        self.assertNotEqual(self._items(production)["cable"].product_id, decoy)

    def test_a_configured_reel_beats_the_name_guess(self):
        self._reel('5/32" 7x19 Cable 500ft Reel')
        chosen = self.env["product.product"].create({
            "name": "House Cable Spool", "type": "consu"})
        self.params.set_param(
            "door_work_order.cable_532_product_id", str(chosen.id))
        production, _r = self.Production._door_wo_create(spec())
        self.assertEqual(self._items(production)["cable"].product_id, chosen)

    def test_lengths_read_in_the_units_the_floor_measures_in(self):
        label = self.Production._door_wo_inches_label
        self.assertEqual(label(76), '76"')
        self.assertEqual(label(76.25), '76 1/4"')
        self.assertEqual(label(76.5), '76 1/2"')
        self.assertEqual(label(76.125), '76 1/8"')
        self.assertEqual(label(76.875), '76 7/8"')
        # Snapped to the nearest eighth, as the calculator's own frac() does,
        # and a value a hair under the next inch must not read as the fraction.
        self.assertEqual(label(76.99), '77"')

    def test_a_door_with_no_weight_is_a_tracks_only_order(self):
        """The calculator cannot work out cables without a door weight.

        It says so on its own screen rather than guessing, so a door sent
        without one is an order for the tracks - not a refusal, and not a cable
        of made-up length.
        """
        production, _r = self.Production._door_wo_create(
            spec(weight=None, cable=None, cable_type=""))
        self.assertEqual(
            set(self._items(production)), {"track_vertical", "track_horizontal"})
        self.assertIn("No cable", production.door_wo_summary)

    def test_pressing_the_button_twice_does_not_build_two_doors(self):
        first, reused = self.Production._door_wo_create(spec())
        self.assertFalse(reused)
        second, reused = self.Production._door_wo_create(spec())
        self.assertTrue(reused)
        self.assertEqual(first, second)

    def test_a_different_mark_is_a_different_door(self):
        first, _r = self.Production._door_wo_create(spec(mark="A"))
        second, reused = self.Production._door_wo_create(spec(mark="B"))
        self.assertFalse(reused)
        self.assertNotEqual(first, second)

    def test_a_finished_order_does_not_block_a_new_one(self):
        first, _r = self.Production._door_wo_create(spec())
        first.state = "cancel"
        second, reused = self.Production._door_wo_create(spec())
        self.assertFalse(reused)
        self.assertNotEqual(first, second)

    def test_the_sender_cannot_choose_a_product(self):
        """THE POINT OF VALIDATING SERVER SIDE.

        The spec describes a DOOR. If a product id in the URL could decide what
        gets booked, a link would be able to name any item in the catalogue -
        so the mapping is read from configuration and anything the sender says
        about products is ignored.
        """
        anything = self.env["product.product"].create({
            "name": "Expensive Thing", "type": "consu"})
        payload = json.loads(spec())
        payload.update({
            "product_id": anything.id,
            "products": [anything.id],
            "job_product_id": anything.id,
        })
        production, _r = self.Production._door_wo_create(json.dumps(payload))
        self.assertNotIn(
            anything, self._items(production).get("track_vertical").product_id)
        self.assertNotEqual(production.product_id, anything)

    def test_a_door_outside_the_calculators_own_limits_is_refused(self):
        for bad, why in [
            ({"width": 500}, "width"),
            ({"height": 2}, "height"),
            ({"vertical": 0}, "vertical"),
            ({"cable": 9999}, "cable"),
        ]:
            with self.assertRaises(UserError, msg=why):
                self.Production._door_wo_create(spec(**bad))

    def test_rubbish_is_refused_rather_than_guessed(self):
        for bad in ["", "not json", "[]", "null", json.dumps({"track": "3-15R"})]:
            with self.assertRaises(UserError):
                self.Production._door_wo_create(bad)

        with self.assertRaises(UserError):
            self.Production._door_wo_create(spec(track="7-99R"))

        with self.assertRaises(UserError):
            self.Production._door_wo_create(spec(width="eighty"))

        with self.assertRaises(UserError):
            self.Production._door_wo_create(spec(cable_type='Cable 9/16"'))

    def test_an_unconfigured_shop_is_told_what_to_set(self):
        """A missing setting must name itself, not fail silently.

        Every part lookup on the tracks feature that went wrong went wrong this
        way - a refusal that named nothing, or named part numbers that existed
        nowhere - so this asserts the message carries the size and where to set
        it.
        """
        self.params.set_param("door_work_order.track_3_product_id", "")
        parsed = self.Production._door_wo_parse(spec())
        _items, missing = self.Production._door_wo_plan(parsed)
        self.assertTrue(missing)
        self.assertIn('3"', missing[0])
        self.assertIn("Settings", missing[0])

        with self.assertRaises(UserError):
            self.Production._door_wo_create(spec())

    def test_no_material_is_booked_unless_asked_for(self):
        production, _r = self.Production._door_wo_create(spec())
        self.assertFalse(
            production.move_raw_ids,
            "material was booked without the setting being turned on")

    def test_material_is_booked_when_asked_for(self):
        self.params.set_param("door_work_order.consume_components", "True")
        self._reel('5/32" 7x19 Cable 500ft Reel')
        production, _r = self.Production._door_wo_create(spec())
        self.assertEqual(len(production.move_raw_ids), 3)
        self.assertEqual(
            sum(production.move_raw_ids.mapped("product_uom_qty")), 6)

    def test_the_order_says_which_door_it_is_for(self):
        production, _r = self.Production._door_wo_create(spec())
        self.assertIn("W-1001", production.origin)
        self.assertEqual(production.door_wo_reference, "W-1001")
        self.assertIn('108" x 84"', production.door_wo_summary)
        self.assertIn('3" 15R', production.door_wo_summary)


@tagged("post_install", "-at_install")
class TestDoorWorkOrderHttp(HttpCase):
    """The two-step flow, over HTTP, as a logged-in employee meets it."""

    def setUp(self):
        super().setUp()
        self.env["res.users"].browse(2).write({"password": "admin"})
        self.track_3 = self.env["product.product"].create({
            "name": '3" Track Stock 20ft', "type": "consu"})
        self.env["ir.config_parameter"].sudo().set_param(
            "door_work_order.track_3_product_id", str(self.track_3.id))

    def _count(self):
        return self.env["mrp.production"].search_count(
            [("door_wo_reference", "=", "W-HTTP")])

    def test_the_review_page_creates_nothing(self):
        """A LINK MUST NOT CHANGE ANYTHING.

        If the calculator's button created the order outright, any page that
        could make a logged-in employee's browser fetch a URL could raise
        manufacturing orders - and a mistyped door would become a record before
        anyone read it. So the link reviews and the POST commits.
        """
        self.authenticate("admin", "admin")
        before = self._count()
        page = self.url_open(
            "/door-work-order/new?spec=%s"
            % http_quote(spec(wo="W-HTTP")))
        self.assertEqual(page.status_code, 200)
        # UNESCAPED, because the page is HTML and an inch mark arrives as
        # &#34;. Asserting on the escaped form would pass for the wrong reason
        # the day the template stops escaping.
        body = html.unescape(page.text)
        self.assertIn("Send this door to manufacturing", body)
        self.assertIn('76"', body)
        self.assertIn('123"', body)
        self.assertIn("Vertical track", body)
        self.env.invalidate_all()
        self.assertEqual(self._count(), before, "a GET created an order")

    def test_the_post_raises_the_order(self):
        self.authenticate("admin", "admin")
        payload = spec(wo="W-HTTP")
        page = self.url_open(
            "/door-work-order/new?spec=%s" % http_quote(payload))
        token = re.search(
            r'name="csrf_token"\s+value="([^"]+)"', page.text)
        self.assertTrue(token, "the review page carried no csrf token")
        done = self.url_open(
            "/door-work-order/create",
            data={"spec": payload, "csrf_token": token.group(1)})
        self.assertEqual(done.status_code, 200)
        self.assertIn("Sent to manufacturing", done.text)
        self.env.invalidate_all()
        self.assertEqual(self._count(), 1)

    def test_a_stranger_gets_the_login_page(self):
        """auth="user" IS the security model, so it is asserted.

        The calculator is a public page and cannot hold a secret, so this
        endpoint is protected by requiring a session rather than by a token
        embedded where anyone can read it.
        """
        page = self.url_open(
            "/door-work-order/new?spec=%s" % http_quote(spec(wo="W-HTTP")),
            allow_redirects=False)
        self.assertIn(page.status_code, (302, 303))
        self.assertIn("/web/login", page.headers.get("Location", ""))


def http_quote(value):
    from urllib.parse import quote

    return quote(value, safe="")


@tagged("post_install", "-at_install")
class TestDoorWorkOrderPapers(DoorWorkOrderCommon):
    """The two sheets the calculator's preview shows, printed from Odoo."""

    def _html(self, production):
        """The rendered paper as a PERSON would read it.

        Unescaped and with runs of whitespace collapsed, because QWeb emits an
        inch mark as &#34; and wraps prose across source lines. Asserting on
        the raw markup passes for the wrong reason the day the template stops
        escaping, and fails for the wrong reason the day it reflows - both of
        which happened here before this helper existed.
        """
        rendered, _kind = self.env["ir.actions.report"]._render_qweb_html(
            "door_work_order.report_info_papers", production.ids)

        if isinstance(rendered, bytes):
            rendered = rendered.decode()

        return re.sub(r"\s+", " ", html.unescape(rendered))

    def test_the_papers_carry_what_the_calculator_showed(self):
        production, _r = self.Production._door_wo_create(spec())
        self.assertEqual(production.door_wo_projection, 6.5)
        self.assertEqual(production.door_wo_ebf, "EBP 3 3/8in")
        self.assertEqual(production.door_wo_capacity, 375)
        self.assertEqual(production.door_wo_ftsc, 85.125)
        self.assertEqual(production.door_wo_config, "3in 15R - Standard Lift")
        self.assertEqual(production.door_wo_cable_type, '5/32"')
        self.assertEqual(
            (production.door_wo_jb_10, production.door_wo_jb_12,
             production.door_wo_jb_14, production.door_wo_jb_16),
            (4, 4, 4, 0),
            "#16 is not called for on this door, so it must read as absent")

    def test_an_overridden_bracket_count_reaches_the_paper(self):
        """THE REASON THESE NUMBERS ARE CARRIED RATHER THAN RECOMPUTED.

        The calculator lets a shop override a jamb bracket quantity in its own
        settings. Recomputing here from the door height would print 4 where the
        screen said 9, and a paper that contradicts the screen it was printed
        from is worse than no paper at all.
        """
        payload = json.loads(spec())
        payload["jb"] = {"j10": 4, "j12": 9, "j14": 4, "j16": 2}
        production, _r = self.Production._door_wo_create(json.dumps(payload))
        self.assertEqual(production.door_wo_jb_12, 9)
        self.assertEqual(production.door_wo_jb_16, 2)
        self.assertIn(">9<", self._html(production).replace(" ", ""))

    def test_both_papers_print_with_their_numbers(self):
        production, _r = self.Production._door_wo_create(spec())
        html = self._html(production)
        self.assertIn("TRACKS", html)
        self.assertIn("CABLES", html)
        # the measurements, in the units the floor reads
        for wanted in ['76"', '96"', '123"', '6 1/2"', '85 1/8"',
                       "D400-144", "EBP 3 3/8in", "W-1001", "3in 15R"]:
            self.assertIn(wanted, html, "the papers omit %r" % wanted)

    def test_the_cables_paper_says_so_when_there_is_no_cable(self):
        """A door sent without a weight has no cable, and the paper says it.

        Printing an empty table would read as "no cable needed" rather than
        "not worked out", and those are different instructions to a person
        holding a reel.
        """
        production, _r = self.Production._door_wo_create(
            spec(weight=None, cable=None, cable_type="", ebf="", capacity=None,
                 ftsc=None))
        html = self._html(production)
        self.assertIn("CABLES", html)
        self.assertIn("no door weight", html)
        self.assertNotIn("Cable Length", html)

    def test_an_order_from_an_older_calculator_still_prints(self):
        """Nothing was refused for lacking the extras, so nothing may crash.

        An order raised before the calculator carried these fields has a
        complete cut list and nothing else. The papers print the rows they
        have and leave out the rows they do not, rather than printing a column
        of blanks that look like measurements.
        """
        payload = json.loads(spec())
        for key in ("projection", "config", "jb", "ebf", "capacity", "ftsc"):
            payload.pop(key)
        production, _r = self.Production._door_wo_create(json.dumps(payload))
        html = self._html(production)
        self.assertIn('76"', html)
        self.assertIn('123"', html)
        self.assertNotIn("2x2 Projection", html)
        self.assertNotIn("EBF", html)

    def test_an_ordinary_manufacturing_order_says_it_has_no_papers(self):
        """The Print entry shows on every MO, so the others must read sensibly."""
        other = self.env["mrp.production"].create({
            "product_id": self.track_3.id, "product_qty": 1.0})
        html = self._html(other)
        self.assertIn("did not come from the door calculator", html)
        self.assertNotIn("TRACKS", html)
