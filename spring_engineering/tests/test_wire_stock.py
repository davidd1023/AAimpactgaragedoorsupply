"""WIRE WE DO NOT STOCK: say so, and say what we do have.

The owner, 2026-10-20: "for any wire sizes we dont stock, we need to implement
a warning that tells the customer that we dont currently stock that wire size
and to try another one that we do stock and then maybe a list or image showing
which wire sizes we do stock. we have these wire sizes: .262 .273 .295 .312
.319 .331 .343 .375 .393 .406".

The calculator answers an engineering question - what wire this door needs -
and that answer is calibrated against thousands of reference readings and is
NOT touched here. What is added is the shop's side of it: we may not have that
wire on the shelf, and the customer cannot know which ones we do.

These read the page's own source, the way _calculator_constants already reads
the steel density out of it: the sizes have to live where the page can warn
about them, and a second copy in Python would be a second thing to forget.
"""

import re

from odoo.tests.common import TransactionCase, tagged
from odoo.tools.misc import file_path

# The owner's list, in his own shorthand, with the wire each one means on the
# calculator's ladder. .262 is 0.2625, .312 is 0.3125, .343 is 0.3437,
# .393 is 0.3938 and .406 is 0.4062 - the same ten wires, said the short way.
OWNERS_LIST = {
    ".262": 0.2625,
    ".273": 0.273,
    ".295": 0.295,
    ".312": 0.3125,
    ".319": 0.3195,
    ".331": 0.331,
    ".343": 0.3437,
    ".375": 0.375,
    ".393": 0.3938,
    ".406": 0.4062,
}


@tagged("post_install", "-at_install")
class WireStockCase(TransactionCase):

    def _source(self, name):
        with open(file_path("spring_engineering/static/src/%s" % name),
                  encoding="utf-8") as handle:
            return handle.read()

    def _numbers(self, name, source):
        found = re.search(r"const %s = \[(.*?)\];" % name, source, re.S)

        self.assertTrue(found, "%s is not in the calculator any more" % name)

        return [float(piece) for piece in found.group(1).replace("\n", "").split(",")
                if piece.strip()]

    # --- the list itself -------------------------------------------------------

    def test_the_ten_sizes_the_owner_named_are_the_stocked_ones(self):
        stocked = self._numbers(
            "STOCKED_WIRE_SIZES", self._source("js/spring_engineering.js"))

        self.assertEqual(sorted(stocked), sorted(OWNERS_LIST.values()))
        self.assertEqual(len(stocked), 10)

    def test_every_stocked_size_is_one_the_calculator_can_quote(self):
        """A size we hold that the model cannot reach would never be offered,
        and the page would send a customer looking for it."""
        source = self._source("js/spring_engineering.js")
        ladder = self._numbers("WIRE_SIZES", source)
        stocked = self._numbers("STOCKED_WIRE_SIZES", source)

        for size in stocked:
            with self.subTest(wire=size):
                self.assertIn(size, ladder,
                              "%s is stocked but is not on the wire ladder" % size)

    def test_the_shorthand_is_not_mistaken_for_the_wire(self):
        """THE TRAP THIS GUARDS: the owner writes .262 and the wire is 0.2625.
        Anybody "correcting" the list to his spelling would drop a size we
        stock and have the page tell customers to choose something else."""
        stocked = self._numbers(
            "STOCKED_WIRE_SIZES", self._source("js/spring_engineering.js"))

        for shorthand, wire in OWNERS_LIST.items():
            with self.subTest(size=shorthand):
                self.assertIn(wire, stocked)

                if wire != float(shorthand):
                    self.assertNotIn(
                        float(shorthand), stocked,
                        "%s was taken for the wire size itself" % shorthand)

    # --- what the page does with it --------------------------------------------

    def test_the_page_warns_about_a_wire_it_cannot_supply(self):
        """Gated on there being something to warn about, and shown for every
        assembly - Duplex has no Wire Size box and still has two wires."""
        page = self._source("xml/spring_engineering.xml")

        self.assertIn("showWireStockWarning", page)
        self.assertIn("We don't currently stock", page)
        self.assertIn("stockedWireLabels", page,
                      "the page does not list what we do stock")

    def test_the_warning_tells_the_customer_what_to_do(self):
        """Two different things, because on Duplex there is nothing to pick:
        change the wire size where there is a box, ring us where there is
        not."""
        page = self._source("xml/spring_engineering.xml")

        self.assertIn("Choose one of the sizes we do stock", page)
        self.assertIn("786-238-7640", page)

    def test_the_wire_the_door_needs_is_not_quietly_changed(self):
        """THE LINE THIS DOES NOT CROSS. The auto-pick walks WIRE_SIZES and
        takes the first that meets the cycle target; stock plays no part in
        it. A calculator that quietly moved to the nearest size we had would
        be answering a different question from the one it is calibrated for -
        and would do it without saying so."""
        source = self._source("js/spring_engineering.js")
        picker = re.search(
            r"for \(const wire of WIRE_SIZES\)(.{0,2000}?)\n    }", source, re.S)

        if picker:
            self.assertNotIn("STOCKED_WIRE_SIZES", picker.group(1),
                             "the wire choice now depends on what is in stock")

        # And the warning reads the chosen wire rather than replacing it.
        self.assertIn("get unstockedWires()", source)
        self.assertIn("isWireStocked", source)

    def test_contact_us_replaces_add_to_cart(self):
        """THE OWNER'S ANSWER, 2026-10-20, to whether a wire we do not stock
        should still be orderable: "when giving the warning about wire size
        change the add to cart button to the contact us button."

        The same answer the shop already gives for a product it will not sell
        off the page, and kinder than a refusal at the end of a cart. One gate
        drives both the warning and the button, so they cannot disagree.
        """
        page = self._source("xml/spring_engineering.xml")
        swap = re.search(
            r'<a t-if="cannotBeSold".*?</button>', page, re.S)

        self.assertTrue(swap, "Add to Cart is still the only button")
        self.assertIn("se-contact-us", swap.group(0))
        self.assertIn("contactUsUrl", swap.group(0))
        self.assertIn("Contact Us", swap.group(0))
        # The ordinary button is the other half of the same choice, so a kit
        # with a stocked wire still goes in a cart.
        self.assertIn('<button t-else=""', swap.group(0))
        self.assertIn("addToCart", swap.group(0))

    def test_contact_us_points_at_the_sites_contact_page(self):
        source = self._source("js/spring_engineering.js")
        found = re.search(
            r'get contactUsUrl\(\) \{.*?return "(.*?)";', source, re.S)

        self.assertTrue(found, "there is nowhere for Contact Us to go")
        self.assertEqual(found.group(1), "/contactus")

    def test_the_styles_exist_in_both_skins(self):
        """The calculator is shown twice: the backend page and the website
        card. A warning styled in one of them only is a warning that looks
        like a bug in the other."""
        for sheet in ("css/spring_engineering.css",
                      "css/spring_engineering_site.css"):
            with self.subTest(sheet=sheet):
                stylesheet = self._source(sheet)
                self.assertIn("se-wire-stock-warning", stylesheet)
                # A link wearing a button's clothes needs the centring and the
                # underline removal a <button> gets for nothing.
                self.assertIn("se-contact-us", stylesheet)


@tagged("post_install", "-at_install")
class DuplexIsNotSoldCase(WireStockCase):
    """DUPLEX IS CALCULATED BUT NOT SOLD (owner, 2026-10-28).

    *"for duplex springs we will leave the option there for people who want to
    use it, but customers will no longer be able to add duplex springs to the
    cart, instead give them a message on the page that will say something like
    we do not currently manufacture custom duplex springs. currently there is
    a message for going under our available wire size, you can replace that
    with the duplex message only for when duplex is selected."*

    Read off the source the same way the wire-stock tests above are, because
    this page is an OWL component with no JS runner in this suite - and the
    server-side refusal, which is the part that actually holds, is tested over
    HTTP in test_add_to_cart.py.
    """

    def test_the_option_is_still_there(self):
        """He asked for it in the same breath: "we will leave the option there
        for people who want to use it". Somebody sizing a duplex they already
        own is exactly who this page is for."""
        source = self._source("js/spring_engineering.js")

        self.assertIn("Duplex", source)
        self.assertIn("DUPLEX_PAIRS", source,
                      "the duplex model has been taken out, not just the sale")

    def test_the_page_says_we_do_not_make_them(self):
        page = self._source("xml/spring_engineering.xml")

        self.assertIn("do not currently manufacture custom duplex springs",
                      page)
        self.assertIn("duplexNotMade", page)

    def test_it_replaces_the_wire_message_rather_than_joining_it(self):
        """"you can replace that with the duplex message only for when duplex
        is selected." A duplex pair often lands on a wire we do not stock
        anyway, and two reasons we cannot sell it is one more than anybody
        needs."""
        source = self._source("js/spring_engineering.js")
        gate = re.search(
            r"get showWireStockWarning\(\) \{.*?\}", source, re.S)

        self.assertTrue(gate, "the wire warning has no gate of its own")
        self.assertIn("!this.duplexNotMade", gate.group(0),
                      "the wire warning still shows on a duplex as well")

    def test_add_to_cart_becomes_contact_us(self):
        source = self._source("js/spring_engineering.js")
        gate = re.search(r"get cannotBeSold\(\) \{.*?\}", source, re.S)

        self.assertTrue(gate, "nothing decides whether it can be sold")
        self.assertIn("duplexNotMade", gate.group(0))
        self.assertIn("unstockedWires", gate.group(0),
                      "the wire reason was dropped on the way")
