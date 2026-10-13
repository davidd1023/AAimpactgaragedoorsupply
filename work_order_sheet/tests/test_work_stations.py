from odoo.exceptions import AccessError, UserError
from odoo.tests.common import HttpCase, tagged

from .test_work_order_sheet import visible_text

SPRING_DESCRIPTION = (
    "Custom Torsion Spring Assembly\n"
    "Duplex, 2 springs\n"
    'Outer: 0.2625" wire, 6" ID, 32.5" long\n'
    'Inner: 0.2253" wire, 3.75" ID, 31.25" long\n'
    "Door: 9' 0\" wide, 7' 0\" high, 355 lb, 10,000 cycles"
)


class StationCase(HttpCase):
    """An order with a spring, a track, a cable and a hinge on it.

    Shared by the tests below rather than inherited from one of them: a test
    class that inherits another runs all of its tests again under a second
    name, which costs time and reports every failure twice.
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

    def _complete(self, station, picking):
        """Dispatch's final confirmation, as the tablet sends it."""
        return self.url_open(
            "/station/%s/complete/%s" % (station.access_token, picking.id),
            data={"tap": "1"})

    def _kiosk(self, station):
        response = self.url_open("/station/%s" % station.access_token)
        self.assertEqual(response.status_code, 200)

        return visible_text(response.text)


@tagged("post_install", "-at_install")
class TestWorkStations(StationCase):
    """Confirming an order puts its work on the bench that does it.

    THE SORT IS THE SHEET'S OWN. _work_order_page already decides whether a
    line is a track, a spring or a cable, and every one of those decisions is
    tested; a station is that page with a tablet in front of it. What is tested
    here is the sorting, the separation between benches, and that a bench can
    tick its work off without being able to touch anybody else's.
    """

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

    def test_hardware_does_not_reach_a_making_bench(self):
        """It goes to Dispatch, which gathers and sends it - see
        TestDispatchIsLast. What it must never do is turn up at a bench that
        winds springs or cuts track."""
        order = self._order()

        for station in (self.springs, self.tracks, self.cables):
            names = self._items(order, station).mapped("name")
            self.assertFalse([n for n in names if "Hinge" in n],
                             "hardware reached %s: %s" % (station.name, names))

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


@tagged("post_install", "-at_install")
class TestStationStatusOnTheOrder(StationCase):
    """The work order says where each bench has got to.

    "Are the springs done?" was answerable only by opening the station queues
    or walking to the bench. The order itself now carries one line per station.
    """

    def test_every_bench_starts_unfinished(self):
        order = self._order()
        picking = order.picking_ids[:1]
        self.assertEqual(picking.work_station_springs, "todo")
        self.assertEqual(picking.work_station_tracks, "todo")
        self.assertEqual(picking.work_station_cables, "todo")

    def test_a_bench_with_no_part_in_the_order_says_nothing(self):
        """Not "To do", which would be a job somebody goes looking for."""
        order = self._order([(self.track, 1, None)])
        picking = order.picking_ids[:1]
        self.assertEqual(picking.work_station_tracks, "todo")
        self.assertEqual(picking.work_station_springs, "none")
        self.assertEqual(picking.work_station_cables, "none")

    def test_finishing_a_bench_shows_on_the_order(self):
        order = self._order()
        picking = order.picking_ids[:1]
        item = self._items(order, self.springs)

        self._tap(self.springs, "done", item)
        picking.invalidate_recordset()

        self.assertEqual(picking.work_station_springs, "done")
        self.assertEqual(picking.work_station_tracks, "todo",
                         "one bench finishing finished them all")

    def test_half_a_bench_reads_in_progress(self):
        """Two of three tracks cut is neither done nor untouched."""
        order = self._order([
            (self.track, 1, None),
            (self.cable, 1, None),
        ])
        # A second track line, so the bench has two jobs on one order.
        second = self.env["product.product"].create({
            "name": '3" Vertical Track 92" - 8\' Door Height Black',
            "type": "consu", "is_storable": True, "list_price": 10.0})
        self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": second.id,
            "product_uom_qty": 1})
        order.picking_ids.action_work_station_sync()

        tracks = self._items(order, self.tracks)
        self.assertEqual(len(tracks), 2, "the bench has only one job")

        tracks[0].action_done()
        picking = order.picking_ids[:1]
        picking.invalidate_recordset()
        self.assertEqual(picking.work_station_tracks, "partial")

        tracks[1].action_done()
        picking.invalidate_recordset()
        self.assertEqual(picking.work_station_tracks, "done")

    def test_undoing_at_the_bench_shows_on_the_order_too(self):
        order = self._order()
        picking = order.picking_ids[:1]
        item = self._items(order, self.cables)

        self._tap(self.cables, "done", item)
        picking.invalidate_recordset()
        self.assertEqual(picking.work_station_cables, "done")

        self._tap(self.cables, "todo", item)
        picking.invalidate_recordset()
        self.assertEqual(picking.work_station_cables, "todo")

    def test_the_count_of_what_is_left_to_make(self):
        """A spring, a track, a cable and the hardware for dispatch."""
        order = self._order()
        picking = order.picking_ids[:1]
        self.assertEqual(picking.work_station_todo_count, 4)

        self._items(order, self.springs).action_done()
        picking.invalidate_recordset()
        self.assertEqual(picking.work_station_todo_count, 3)

    def test_the_status_can_be_searched_rather_than_opened(self):
        """Stored, so the office can filter a list of orders by it."""
        order = self._order()
        picking = order.picking_ids[:1]
        self.assertIn(picking, self.env["stock.picking"].search(
            [("work_station_springs", "=", "todo")]))

        self._items(order).action_done()
        picking.invalidate_recordset()
        self.assertIn(picking, self.env["stock.picking"].search(
            [("work_station_todo_count", "=", 0)]))

    def test_the_stat_button_opens_this_orders_rows_only(self):
        first = self._order()
        second = self._order()
        action = first.picking_ids[:1].action_open_work_station_items()
        found = self.env["work.station.item"].search(action["domain"])
        self.assertEqual(found, self._items(first))
        self.assertFalse(found & self._items(second))


@tagged("post_install", "-at_install")
class TestDispatchIsLast(StationCase):
    """Dispatch gathers the hardware, goes last, and finishes the order.

    The owner's rule: "dispatch will be the last thing workers do after the
    other three are done", and when it is done the work order is done. Both
    halves are enforced here rather than left to how people happen to work.
    """

    def setUp(self):
        super().setUp()
        self.dispatch = self.env.ref("work_order_sheet.station_dispatch")

    def test_the_hardware_goes_to_dispatch(self):
        """What used to be nobody's job is now the last bench's."""
        order = self._order()
        items = self._items(order, self.dispatch)
        self.assertEqual(items.mapped("name"), ["No 2 Hinge Galvanized"])

    def test_dispatch_waits_for_the_making_benches(self):
        order = self._order()
        item = self._items(order, self.dispatch)
        self.assertFalse(item.is_ready)
        self.assertIn("Springs", item.waiting_for)
        self.assertIn("Tracks", item.waiting_for)
        self.assertIn("Cables", item.waiting_for)

    def test_dispatch_cannot_be_ticked_off_early(self):
        order = self._order()
        item = self._items(order, self.dispatch)

        with self.assertRaises(UserError):
            item.action_done()

        self.assertEqual(item.state, "todo")

    def test_the_kiosk_shows_what_it_is_waiting_for_instead_of_a_button(self):
        self._order()
        page = self._kiosk(self.dispatch)
        self.assertIn("No 2 Hinge", page)
        self.assertIn("Waiting for", page)
        self.assertNotIn("Done", page,
                         "dispatch was offered a button it must not have yet")

    def test_tapping_done_too_early_explains_itself_instead_of_breaking(self):
        """A bench tablet must never show a traceback."""
        order = self._order()
        item = self._items(order, self.dispatch)
        response = self.url_open(
            "/station/%s/done/%s" % (self.dispatch.access_token, item.id),
            data={"tap": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("is the last step", visible_text(response.text))
        self.assertIn(self.dispatch.name, visible_text(response.text))
        self.assertEqual(item.state, "todo")

    def test_dispatch_opens_once_the_others_are_finished(self):
        order = self._order()
        making = self._items(order) - self._items(order, self.dispatch)
        making.action_done()

        item = self._items(order, self.dispatch)
        self.assertTrue(item.is_ready)
        self.assertFalse(item.waiting_for)
        self.assertIn("Done", self._kiosk(self.dispatch))

    def test_hardware_alone_is_ready_at_once(self):
        """A bench with nothing to make is not in the way: an order of
        hardware alone could otherwise never leave."""
        order = self._order([(self.hinge, 4, None)])
        item = self._items(order, self.dispatch)
        self.assertTrue(item.is_ready)

    # --- and then the order is done -------------------------------------------

    def test_ticking_off_the_last_box_does_not_send_the_order_out(self):
        """It used to. A button that fires by itself confirms nothing, and the
        last tap on a tablet is a clumsy place for an irreversible step."""
        order = self._order([(self.hinge, 4, None)])
        picking = order.picking_ids[:1]
        picking.action_assign()
        self._items(order).action_done()
        picking.invalidate_recordset()

        self.assertEqual(picking.work_station_dispatch, "done")
        self.assertNotEqual(picking.state, "done",
                            "the order closed without anybody confirming it")

    def test_completing_it_finishes_the_work_order(self):
        order = self._order([(self.hinge, 4, None)])
        picking = order.picking_ids[:1]
        picking.action_assign()
        self._items(order).action_done()

        self.assertEqual(picking._work_station_complete(), "")
        picking.invalidate_recordset()
        self.assertEqual(picking.state, "done")

    def test_an_unfinished_order_cannot_be_completed(self):
        order = self._order()
        picking = order.picking_ids[:1]

        with self.assertRaises(UserError):
            picking._work_station_complete()

        picking.invalidate_recordset()
        self.assertNotEqual(picking.state, "done")

    def test_the_whole_order_through_every_bench_in_turn(self):
        """The flow as it actually happens, one bench at a time."""
        order = self._order()
        picking = order.picking_ids[:1]
        picking.action_assign()

        for station in (self.springs, self.tracks, self.cables):
            self._items(order, station).action_done()
            picking.invalidate_recordset()
            self.assertNotEqual(picking.state, "done",
                                "the order finished before dispatch did")

        self._items(order, self.dispatch).action_done()
        picking.invalidate_recordset()
        self.assertNotEqual(picking.state, "done",
                            "dispatch has not confirmed it yet")

        picking._work_station_complete()
        picking.invalidate_recordset()
        self.assertEqual(picking.state, "done")

    def test_an_order_that_cannot_be_validated_keeps_the_work_and_says_why(self):
        """A transfer Odoo refuses unattended must not lose the bench's work
        or put an error on the screen at the bench.

        A lot-tracked product is the honest example: Odoo will not invent a
        serial number, and nor should this.
        """
        tracked = self.env["product.product"].create({
            "name": "Tracked Hinge", "type": "consu", "is_storable": True,
            "tracking": "serial", "list_price": 10.0,
        })
        order = self._order([(tracked, 2, None)])
        picking = order.picking_ids[:1]

        self._items(order).action_done()
        reason = picking._work_station_complete()
        picking.invalidate_recordset()

        self.assertTrue(reason, "the bench was told nothing")

        self.assertEqual(self._items(order).mapped("state"), ["done"],
                         "the bench's work was lost")
        self.assertNotEqual(picking.state, "done")
        self.assertTrue(
            picking.message_ids.filtered(
                lambda m: "could not be validated automatically" in (m.body or "")),
            "nobody in the office was told")

    # --- the final confirmation, from the bench -------------------------------

    def test_the_button_appears_only_when_everything_is_done(self):
        order = self._order()
        picking = order.picking_ids[:1]
        picking.action_assign()

        self.assertNotIn("Complete order", self._kiosk(self.dispatch),
                         "offered before the work was finished")

        self._items(order).action_done()

        page = self._kiosk(self.dispatch)
        self.assertIn("Ready to send out", page)
        self.assertIn("Complete order", page)

    def test_pressing_it_completes_the_order_and_says_so(self):
        order = self._order([(self.hinge, 4, None)])
        picking = order.picking_ids[:1]
        picking.action_assign()
        self._items(order).action_done()

        response = self._complete(self.dispatch, picking)
        self.assertEqual(response.status_code, 200)
        picking.invalidate_recordset()
        self.assertEqual(picking.state, "done")

        text = visible_text(response.text)
        self.assertIn("is complete and on its way", text)
        # And it has left the screen, rather than sitting there to be pressed
        # again.
        self.assertNotIn("Complete order", text)

    def test_only_dispatch_is_offered_the_button(self):
        """Every bench finishes its own work; one says the order is finished."""
        order = self._order()
        picking = order.picking_ids[:1]
        picking.action_assign()
        self._items(order).action_done()

        for station in (self.springs, self.tracks, self.cables):
            self.assertNotIn("Complete order", self._kiosk(station),
                             "%s was offered it" % station.name)
            self.assertEqual(
                self._complete(station, picking).status_code, 404,
                "%s could complete an order" % station.name)

        picking.invalidate_recordset()
        self.assertNotEqual(picking.state, "done")

    def test_dispatch_cannot_complete_an_unfinished_order(self):
        """Finishing one order must not offer up the next one."""
        mine = self._order([(self.hinge, 1, None)])
        theirs = self._order([(self.hinge, 1, None)])
        self._items(mine).action_done()

        other = theirs.picking_ids[:1]
        self.assertEqual(self._complete(self.dispatch, other).status_code, 404)
        other.invalidate_recordset()
        self.assertNotEqual(other.state, "done")

    def test_an_order_with_nothing_for_dispatch_can_still_be_completed(self):
        """THE BUG: an order of nothing but tracks - cut, ticked off,
        finished - never reached this screen, so nobody on the floor could
        close it. Dispatch is the step that sends an order out; having nothing
        to gather for it does not make it somebody else's to close."""
        order = self._order([(self.track, 2, None), (self.cable, 2, None)])
        picking = order.picking_ids[:1]
        picking.action_assign()
        self.assertEqual(picking.work_station_dispatch, "none",
                         "the fixture put something on dispatch")

        self._items(order).action_done()

        page = self._kiosk(self.dispatch)
        self.assertIn("Ready to send out", page)
        self.assertIn("Nothing here to gather", page)

        self._complete(self.dispatch, picking)
        picking.invalidate_recordset()
        self.assertEqual(picking.state, "done")

    def test_an_order_of_springs_alone_can_be_completed(self):
        order = self._order([(self.spring, 1, SPRING_DESCRIPTION)])
        picking = order.picking_ids[:1]
        picking.action_assign()
        self._items(order).action_done()

        self._complete(self.dispatch, picking)
        picking.invalidate_recordset()
        self.assertEqual(picking.state, "done")

    def test_a_transfer_with_no_bench_work_is_none_of_dispatchs_business(self):
        """What keeps every unrelated transfer in the warehouse off the
        screen."""
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.env["stock.picking.type"].search(
                [("code", "=", "internal")], limit=1).id,
            "location_id": self.env.ref("stock.stock_location_stock").id,
            "location_dest_id": self.env.ref("stock.stock_location_output").id,
        })
        picking.action_confirm()

        self.assertFalse(picking.work_station_item_ids)
        self.assertEqual(self._complete(self.dispatch, picking).status_code,
                         404)
        self.assertNotIn(picking.name, self._kiosk(self.dispatch))

    def test_pressing_it_too_early_is_refused_over_the_wire_too(self):
        """The page hides the button; the route does not rely on that."""
        order = self._order()
        picking = order.picking_ids[:1]
        self.assertEqual(self._complete(self.dispatch, picking).status_code, 404)
        picking.invalidate_recordset()
        self.assertNotEqual(picking.state, "done")

    def test_a_completed_order_leaves_every_bench_screen(self):
        order = self._order([(self.hinge, 1, None)])
        picking = order.picking_ids[:1]
        picking.action_assign()
        self._items(order).action_done()
        self._complete(self.dispatch, picking)

        self.assertIn("Nothing waiting", self._kiosk(self.dispatch))


@tagged("post_install", "-at_install")
class TestTheOrdersLog(StationCase):
    """When a section of the order was finished, written where it is kept.

    The statuses say where each bench has got to; they cannot say the springs
    were done at 10:42 and the tracks at 14:05. That is a question about a
    day's work, and the answer belongs in the order's own log.
    """

    def setUp(self):
        super().setUp()
        self.dispatch = self.env.ref("work_order_sheet.station_dispatch")

    def _log(self, picking):
        return [m.body or "" for m in picking.message_ids]

    def _notes(self, picking):
        note = self.env.ref("mail.mt_note")

        return picking.message_ids.filtered(lambda m: m.subtype_id == note)

    def test_finishing_a_job_is_written_into_the_order(self):
        order = self._order()
        picking = order.picking_ids[:1]
        self._items(order, self.springs).action_done()

        entry = self._log(picking)[0]
        self.assertIn("Springs", entry)
        self.assertIn("Custom Torsion Spring Assembly", entry)

    def test_the_entry_is_dated_by_the_log_itself(self):
        order = self._order()
        picking = order.picking_ids[:1]
        item = self._items(order, self.tracks)
        item.action_done()

        entry = picking.message_ids[0]
        self.assertTrue(entry.date)
        # The same moment the row records, so the two cannot disagree.
        self.assertAlmostEqual(
            (entry.date - item.done_at).total_seconds(), 0, delta=5)

    def test_it_says_when_a_bench_has_finished_the_whole_section(self):
        """The line somebody looking for "when were the springs done" wants."""
        order = self._order()
        picking = order.picking_ids[:1]
        self._items(order, self.springs).action_done()
        self.assertIn("has finished every job on this order",
                      self._log(picking)[0])

    def test_a_bench_with_more_to_do_does_not_claim_to_be_finished(self):
        order = self._order([(self.track, 1, None)])
        second = self.env["product.product"].create({
            "name": '3" Vertical Track 92" - 8\' Door Height Black',
            "type": "consu", "is_storable": True, "list_price": 10.0})
        self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": second.id,
            "product_uom_qty": 1})
        order.picking_ids.action_work_station_sync()
        picking = order.picking_ids[:1]

        tracks = self._items(order, self.tracks)
        tracks[0].action_done()
        self.assertNotIn("has finished every job", self._log(picking)[0])

        tracks[1].action_done()
        self.assertIn("has finished every job", self._log(picking)[0])

    def test_four_jobs_ticked_at_once_leave_one_entry(self):
        """A day's log should read as a sequence of events, not a list of
        rows."""
        order = self._order([(self.hinge, 1, None)])
        extra = self.env["product.product"].create({
            "name": "No 3 Hinge Galvanized", "type": "consu",
            "is_storable": True, "list_price": 10.0})
        self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": extra.id,
            "product_uom_qty": 1})
        order.picking_ids.action_work_station_sync()
        picking = order.picking_ids[:1]
        before = len(self._notes(picking))

        self._items(order, self.dispatch).action_done()

        self.assertEqual(len(self._notes(picking)) - before, 1)
        self.assertIn("No 2 Hinge", self._log(picking)[0])
        self.assertIn("No 3 Hinge", self._log(picking)[0])

    def test_undoing_is_logged_too(self):
        """A log that recorded only the ticking off would show work finished
        that is being done again."""
        order = self._order()
        picking = order.picking_ids[:1]
        item = self._items(order, self.cables)
        item.action_done()
        item.action_todo()

        self.assertIn("put back", self._log(picking)[0])
        self.assertIn("Cables", self._log(picking)[0])

    def test_the_log_is_internal_and_never_mailed_to_the_customer(self):
        order = self._order()
        picking = order.picking_ids[:1]
        self._items(order, self.springs).action_done()

        note = self.env.ref("mail.mt_note")
        self.assertEqual(picking.message_ids[0].subtype_id, note,
                         "the customer was sent a bench update")

    def test_completing_the_order_is_logged(self):
        order = self._order([(self.hinge, 1, None)])
        picking = order.picking_ids[:1]
        picking.action_assign()
        self._items(order).action_done()
        picking._work_station_complete()

        self.assertIn("confirmed this order as complete", self._log(picking)[0])
        self.assertIn(self.dispatch.name, self._log(picking)[0])

    def test_a_tap_at_the_bench_reaches_the_log(self):
        """End to end: the tablet, not the model."""
        order = self._order()
        picking = order.picking_ids[:1]
        item = self._items(order, self.tracks)

        self._tap(self.tracks, "done", item)

        self.assertTrue(
            picking.message_ids.filtered(
                lambda m: "Tracks" in (m.body or "")),
            "the tablet's tap was not written down")

    def test_the_log_quotes_the_length_that_was_cut(self):
        order = self._order()
        picking = order.picking_ids[:1]
        self._items(order, self.tracks).action_done()
        self.assertIn('76"', self._log(picking)[0])




@tagged("post_install", "-at_install")
class TestSuppliedAsStock(StationCase):
    """Perforated angles, shafts and trims arrive complete.

    The owner's rule: they are supplied as they come, so dispatch has no work
    to do on them, nobody ticks them off - and because nothing was done, there
    is nothing to put back.
    """

    def setUp(self):
        super().setUp()
        self.dispatch = self.env.ref("work_order_sheet.station_dispatch")

    def _product(self, name):
        return self.env["product.product"].create({
            "name": name, "type": "consu", "is_storable": True,
            "list_price": 10.0})

    def _one(self, name):
        order = self._order([(self._product(name), 2, None)])

        return order, self._items(order, self.dispatch)

    # --- what counts ----------------------------------------------------------

    def test_the_three_kinds_arrive_complete(self):
        for name in ('2" x 2" Perforated Angle 10ft Galvanized',
                     'Perforated Angle, 14 Gauge',
                     '1" Torsion Shaft 8ft',
                     'Shafts, Keyed 1 Inch',
                     "White Trims",
                     'Plastic Trim 18ft Almond'):
            _order, item = self._one(name)
            self.assertEqual(item.state, "done", name)
            self.assertTrue(item.auto_done, name)
            self.assertTrue(item.done_at, name)

    def test_a_flag_angle_is_not_a_perforated_angle(self):
        """THE ONE MISTAKE THIS MUST NOT MAKE. A flag angle is real work on a
        prepared track - the calculator adds one per track - so matching on
        "angle" alone would have marked them complete and sent somebody a door
        with no flag angle fitted."""
        for name in ("Flag Angle Black", "Flag Angle White",
                     'Angle Bracket 2"'):
            _order, item = self._one(name)
            self.assertFalse(item.auto_done, name)
            self.assertEqual(item.state, "todo", name)

    def test_ordinary_hardware_still_has_to_be_gathered(self):
        _order, item = self._one("No 2 Hinge Galvanized")
        self.assertFalse(item.auto_done)
        self.assertEqual(item.state, "todo")

    def test_only_dispatch_hands_out_free_passes(self):
        """A property of a part that is gathered, not of one that is made: if
        a name like this ever sorts to a making bench, that bench is doing
        something to it and still says when it is done."""
        order = self._order([(self._product('2" Track Shaft Assembly'), 1, None)])
        item = self._items(order, self.tracks)
        self.assertTrue(item, "the fixture did not reach the tracks bench")
        self.assertFalse(item.auto_done)
        self.assertEqual(item.state, "todo")

    # --- and they cannot be undone -------------------------------------------

    def test_they_cannot_be_put_back(self):
        _order, item = self._one("White Trims")

        with self.assertRaises(UserError):
            item.action_todo()

        self.assertEqual(item.state, "done")

    def test_the_kiosk_offers_no_button_for_them(self):
        self._one("White Trims")
        page = self._kiosk(self.dispatch)
        self.assertIn("Already complete", page)
        self.assertIn("White Trims", page)
        self.assertNotIn("Undo", page)

    def test_the_route_refuses_to_put_one_back(self):
        """The page offers no button; the route does not rely on that."""
        _order, item = self._one("White Trims")
        response = self.url_open(
            "/station/%s/todo/%s" % (self.dispatch.access_token, item.id),
            data={"tap": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("nothing to put back", visible_text(response.text))
        self.assertEqual(item.state, "done")

    # --- the order they are on ------------------------------------------------

    def test_the_order_still_waits_for_the_complete_button(self):
        """The owner's note: an order of nothing but these still has to be
        completed by hand at dispatch. Arriving complete is not the same as
        being sent out."""
        order = self._order([(self._product("White Trims"), 2, None)])
        picking = order.picking_ids[:1]
        picking.action_assign()

        self.assertEqual(picking.work_station_dispatch, "done")
        self.assertNotEqual(picking.state, "done",
                            "the order sent itself out")

        page = self._kiosk(self.dispatch)
        self.assertIn("Ready to send out", page)
        self.assertIn("Complete order", page)

        self._complete(self.dispatch, picking)
        picking.invalidate_recordset()
        self.assertEqual(picking.state, "done")

    def test_they_do_not_hold_up_the_rest_of_the_order(self):
        order = self._order([
            (self._product("White Trims"), 2, None),
            (self.hinge, 4, None),
        ])
        picking = order.picking_ids[:1]
        self.assertEqual(picking.work_station_dispatch, "partial",
                         "a free pass counted as the whole section")

        self._items(order, self.dispatch).filtered(
            lambda item: not item.auto_done).action_done()
        picking.invalidate_recordset()
        self.assertEqual(picking.work_station_dispatch, "done")

    def test_the_log_says_why_nobody_ticked_them_off(self):
        order, _item = self._one("White Trims")
        picking = order.picking_ids[:1]
        entry = picking.message_ids.filtered(
            lambda m: "Complete on arrival" in (m.body or ""))
        self.assertTrue(entry, "the log does not explain itself")
        self.assertIn("White Trims", entry[0].body)

    def test_sorting_again_does_not_say_it_twice(self):
        order, _item = self._one("White Trims")
        picking = order.picking_ids[:1]
        before = len(picking.message_ids)

        picking.action_work_station_sync()

        self.assertEqual(len(picking.message_ids), before)
