from odoo.exceptions import AccessError
from odoo.tests.common import HttpCase, tagged

from .test_work_order_sheet import visible_text

SPRING_DESCRIPTION = (
    "Custom Torsion Spring Assembly\n"
    "Duplex, 2 springs\n"
    'Outer: 0.2625" wire, 6" ID, 32.5" long\n'
    'Inner: 0.2253" wire, 3.75" ID, 31.25" long\n'
    "Door: 9' 0\" wide, 7' 0\" high, 355 lb, 10,000 cycles"
)


@tagged("post_install", "-at_install")
class TestWorkStations(HttpCase):
    """Confirming an order puts its work on the bench that does it.

    THE SORT IS THE SHEET'S OWN. _work_order_page already decides whether a
    line is a track, a spring or a cable, and every one of those decisions is
    tested; a station is that page with a tablet in front of it. What is tested
    here is the sorting, the separation between benches, and that a bench can
    tick its work off without being able to touch anybody else's.
    """

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "A Customer"})
        self.springs = self.env.ref("work_order_sheet.station_springs")
        self.tracks = self.env.ref("work_order_sheet.station_tracks")
        self.cables = self.env.ref("work_order_sheet.station_cables")

        def product(name, code=False):
            return self.env["product.product"].create({
                "name": name, "default_code": code, "type": "consu",
                "is_storable": True, "list_price": 10.0,
            })

        self.spring = product("Custom Torsion Spring Assembly")
        self.track = product('2" Vertical Track 76" - 7\' Door Height Black',
                             "CH-VT-2")
        self.cable = product('1/8" 7X19 GAC Lift Cable 110" Black', "GAC-110")
        self.hinge = product("No 2 Hinge Galvanized", "HN-2")

    def _order(self, products=None):
        products = products or [
            (self.spring, 1, SPRING_DESCRIPTION),
            (self.track, 2, None),
            (self.cable, 2, None),
            (self.hinge, 8, None),
        ]
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [
                (0, 0, dict({
                    "product_id": product.id, "product_uom_qty": qty,
                }, **({"name": name} if name else {})))
                for product, qty, name in products
            ],
        })
        order.action_confirm()

        return order

    def _items(self, order, station=None):
        domain = [("picking_id", "in", order.picking_ids.ids)]

        if station:
            domain.append(("station_id", "=", station.id))

        return self.env["work.station.item"].search(domain)

    # --- the sort -------------------------------------------------------------

    def test_confirming_an_order_sorts_its_work_onto_the_benches(self):
        order = self._order()
        self.assertTrue(order.picking_ids, "the order made no transfer")

        by_station = {}

        for item in self._items(order):
            by_station.setdefault(item.station_id.code, []).append(item.name)

        self.assertIn("springs", by_station)
        self.assertIn("tracks", by_station)
        self.assertIn("cables", by_station)
        self.assertEqual(len(by_station["springs"]), 1)

    def test_hardware_is_not_a_station(self):
        """Hinges come off a shelf against the transfer, as they always did."""
        order = self._order()
        names = self._items(order).mapped("name")
        self.assertFalse([n for n in names if "Hinge" in n],
                         "hardware reached a bench: %s" % names)

    def test_the_spring_carries_its_cut_list_and_its_door(self):
        item = self._items(self._order(), self.springs)
        self.assertEqual(len(item), 1)
        self.assertIn('0.2625" wire', item.detail)
        self.assertIn("Duplex", item.detail)
        self.assertIn("355 lb", item.door)
        self.assertIn("9' 0\"", item.door)

    def test_the_track_carries_the_length_to_cut(self):
        item = self._items(self._order(), self.tracks)
        self.assertEqual(item.length, '76"',
                         "the bench was not told what to cut: %r" % item.length)

    def test_sorting_again_neither_doubles_the_queue_nor_unfinishes_it(self):
        order = self._order()
        before = self._items(order)
        before.filtered(lambda i: i.station_id == self.tracks).action_done()

        order.picking_ids.action_work_station_sync()

        after = self._items(order)
        self.assertEqual(len(after), len(before), "the queue doubled")
        self.assertEqual(
            self._items(order, self.tracks).mapped("state"), ["done"],
            "a re-sort un-finished work that was already done")

    # --- one bench cannot see another ----------------------------------------

    def _tap(self, station, action, item):
        """What a bench tablet does when somebody presses a button.

        A BODY, BECAUSE AN EMPTY ONE IS A GET. url_open posts only when there
        is something to post, so data={} goes out as a GET and the route
        refuses it with a 405 - which looks exactly like a passing security
        test and is not one.
        """
        return self.url_open(
            "/station/%s/%s/%s" % (station.access_token, action, item.id),
            data={"tap": "1"})

    def _kiosk(self, station):
        response = self.url_open("/station/%s" % station.access_token)
        self.assertEqual(response.status_code, 200)

        return visible_text(response.text)

    def test_a_bench_sees_its_own_work_and_nobody_elses(self):
        self._order()
        springs = self._kiosk(self.springs)
        tracks = self._kiosk(self.tracks)

        self.assertIn("Custom Torsion Spring Assembly", springs)
        self.assertIn('0.2625"', springs, "the bench cannot see the spec")

        self.assertIn("Vertical Track", tracks)
        self.assertNotIn("Custom Torsion Spring Assembly", tracks,
                         "the track bench can see the springs")
        self.assertNotIn('0.2625"', tracks,
                         "the track bench can read the spring specification")
        self.assertNotIn("GAC", tracks, "the track bench can see the cables")

    def test_the_door_is_on_every_bench_that_builds_for_it(self):
        """A track cutter is cutting for the same door the spring is wound for."""
        self._order()
        self.assertIn("355 lb", self._kiosk(self.tracks))

    def test_a_wrong_link_shows_nothing(self):
        self._order()
        self.assertEqual(self.url_open("/station/not-a-token").status_code, 404)
        self.assertEqual(
            self.url_open("/station/%s" % ("f" * 64)).status_code, 404)

    def test_a_bench_cannot_tick_off_another_benchs_work(self):
        """THE WHOLE SECURITY MODEL, since there is no login: the link names
        the station, and an item is checked against it rather than trusted."""
        order = self._order()
        spring_item = self._items(order, self.springs)

        response = self.url_open(
            "/station/%s/done/%s" % (self.tracks.access_token, spring_item.id),
            data={"tap": "1"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(spring_item.state, "todo",
                         "another bench finished the spring")

    # --- ticking work off -----------------------------------------------------

    def test_done_takes_it_off_the_list_and_undo_puts_it_back(self):
        order = self._order()
        item = self._items(order, self.springs)

        self.url_open("/station/%s/done/%s" % (self.springs.access_token, item.id),
                      data={"tap": "1"})
        item.invalidate_recordset()
        self.assertEqual(item.state, "done")
        self.assertTrue(item.done_at)

        page = self._kiosk(self.springs)
        self.assertIn("Finished today", page)
        self.assertIn("Undo", page)

        self.url_open("/station/%s/todo/%s" % (self.springs.access_token, item.id),
                      data={"tap": "1"})
        item.invalidate_recordset()
        self.assertEqual(item.state, "todo")
        self.assertFalse(item.done_at)

    def test_an_empty_bench_says_so(self):
        self.assertIn("Nothing waiting", self._kiosk(self.cables))

    def test_replacing_the_link_kills_the_old_one(self):
        self._order()
        old = self.springs.access_token
        self.springs.action_regenerate_token()
        self.assertNotEqual(self.springs.access_token, old)
        self.assertEqual(self.url_open("/station/%s" % old).status_code, 404)
        self.assertEqual(
            self.url_open("/station/%s" % self.springs.access_token).status_code,
            200)


@tagged("post_install", "-at_install")
class TestWhereTheStationsLive(HttpCase):
    """The benches are under Manufacturing, and the people who run the floor
    can reach them.

    A MANUFACTURING ADMINISTRATOR IS NOT AN INVENTORY ONE. mrp.group_mrp_user
    implies stock.group_stock_user and nothing more, so permissions granted
    only to the Inventory groups would have hidden the kiosk links from
    exactly the person whose floor this is.
    """

    def test_the_menus_hang_under_manufacturing(self):
        for menu, parent in (
            ("work_order_sheet.menu_work_station_item",
             "mrp.menu_mrp_manufacturing"),
            ("work_order_sheet.menu_work_station",
             "mrp.menu_mrp_configuration"),
        ):
            self.assertEqual(self.env.ref(menu).parent_id,
                             self.env.ref(parent), menu)

    def test_a_manufacturing_user_can_read_the_queue(self):
        user = self.env["res.users"].create({
            "name": "Bench Supervisor", "login": "bench-supervisor",
            "group_ids": [(6, 0, [self.env.ref("mrp.group_mrp_user").id])],
        })
        items = self.env["work.station.item"].with_user(user)
        self.assertEqual(items.search_count([]), items.sudo().search_count([]))

    def test_a_manufacturing_administrator_can_replace_a_kiosk_link(self):
        user = self.env["res.users"].create({
            "name": "Floor Manager", "login": "floor-manager",
            "group_ids": [(6, 0, [self.env.ref("mrp.group_mrp_manager").id])],
        })
        station = self.env.ref("work_order_sheet.station_springs").with_user(user)
        before = station.access_token
        station.action_regenerate_token()
        self.assertNotEqual(station.access_token, before)

    def test_an_ordinary_user_cannot_read_a_kiosk_link(self):
        """It is the key to a bench, so it is not something to leave lying in
        a list view for everybody with stock access."""
        user = self.env["res.users"].create({
            "name": "Picker", "login": "bench-picker",
            "group_ids": [(6, 0, [self.env.ref("stock.group_stock_user").id])],
        })
        station = self.env.ref("work_order_sheet.station_springs").with_user(user)

        with self.assertRaises(AccessError):
            station.access_token

        with self.assertRaises(AccessError):
            station.kiosk_url

        # The station itself is still readable - a picker may see the name.
        self.assertEqual(station.name, "Springs")
