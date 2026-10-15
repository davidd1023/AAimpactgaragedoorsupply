import math
import re

from odoo import _, models
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.tools.misc import formatLang

from .sale_order_line import FASTENER_ROLES

# The attribute value that means "send it ready to fit". Matched on the VALUE's
# name rather than on an xml id, so the owner can attach the attribute to track
# products by hand - which is how the other product options on these pages are
# set up - without the code needing to know which products those are.
PREPARED = "prepared"


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # --- the least this shop will take as an order ----------------------------
    #
    # SAID ONCE, WHERE EVERY WAY OUT OF THE CART ALREADY ASKS. Odoo's own
    # question is _is_cart_ready, and it is asked in three places that matter:
    # the checkout button keys its `disabled` on it, the payment routes call
    # _check_cart_is_ready_to_be_paid which calls it, and the cart page passes
    # it to the template. Answering it is therefore the whole of the rule -
    # there is no fourth door to bolt, and nothing to keep in step.
    #
    # The amount is a WEBSITE setting, so an order with no website - anything
    # raised in the back office - has no minimum and is never held up by this.

    def _aa_amount_for_minimum(self):
        """What counts towards the minimum: the goods, before tax.

        DELIVERY DOES NOT COUNT, and neither does tax. A minimum order is about
        how much is being bought, and letting the shipping charge make up the
        difference would mean a far-away customer qualifies with a smaller
        order than one next door. This is the Subtotal the cart page shows, so
        the figure the customer is asked to reach is the figure in front of
        them.
        """
        self.ensure_one()

        return sum(
            line.price_subtotal
            for line in self.order_line
            if not line.is_delivery and not line.display_type
        )

    def _aa_minimum_shortfall(self):
        """How much this cart is short, or 0 when it may be checked out.

        AN EMPTY CART IS NOT "SHORT". It cannot be checked out either, but Odoo
        says that for itself and the cart page says so in plain words; adding
        "spend another $500" to an empty cart would be two messages about the
        same nothing.
        """
        self.ensure_one()

        minimum = self.website_id.aa_minimum_order_amount or 0.0

        if minimum <= 0 or not self.order_line:
            return 0.0

        goods = self._aa_amount_for_minimum()
        currency = self.currency_id or self.website_id.currency_id

        # COMPARED IN MONEY, NOT IN FLOATING POINT. A cart of exactly the
        # minimum can land a hundredth of a cent under it once a few lines
        # have been added up, and refusing that order - with a message asking
        # for $0.00 more - is indefensible.
        if currency and currency.compare_amounts(goods, minimum) >= 0:
            return 0.0

        if not currency and goods >= minimum:
            return 0.0

        return minimum - goods

    def _is_cart_ready(self):
        return super()._is_cart_ready() and not self._aa_minimum_shortfall()

    def _check_cart_is_ready_to_be_paid(self):
        """Say which rule stopped it, rather than "verify previous steps".

        Odoo's message for a cart that is not ready has to cover every reason
        at once, so it names none of them. A customer who cannot pay because
        of a rule nobody has told them about has no way to work out what to do
        next, and the honest answer is short.
        """
        shortfall = self._aa_minimum_shortfall()

        if shortfall:
            raise ValidationError(_(
                "Orders start at %(minimum)s. Your cart comes to %(total)s,"
                " so please add %(short)s more before checking out.",
                minimum=self._aa_money(
                    self.website_id.aa_minimum_order_amount),
                total=self._aa_money(self._aa_amount_for_minimum()),
                short=self._aa_money(shortfall),
            ))

        return super()._check_cart_is_ready_to_be_paid()

    def _allow_express_checkout(self):
        """The express buttons are a door of their own.

        Apple Pay and the like skip the cart's own button entirely, so a
        minimum that only disabled that button would be no minimum at all for
        anybody who used them.
        """
        return (super()._allow_express_checkout()
                and not self._aa_minimum_shortfall())

    def _aa_money(self, amount):
        """An amount as the customer reads it, for a message."""
        self.ensure_one()
        currency = self.currency_id or self.website_id.currency_id

        return formatLang(self.env, amount or 0.0,
                          currency_obj=currency) if currency else "%.2f" % (
            amount or 0.0)

    # THE PRODUCTS WHOSE PRICE IS CONFIGURED, NOT LISTED. Both deliberately
    # list at zero: what they cost is worked out by the calculator from cone,
    # steel, labour and markup, and written onto the line.
    CONFIGURED_PRICE_PRODUCTS = (
        "spring_engineering.product_custom_spring",
        "spring_engineering.product_custom_filler",
    )

    def _door_configured_price_products(self):
        products = self.env["product.product"]

        for ref in self.CONFIGURED_PRICE_PRODUCTS:
            template = self.env.ref(ref, raise_if_not_found=False)

            if template:
                products |= template.sudo().product_variant_ids

        return products

    def _get_update_prices_lines(self):
        """Leave a configured assembly's price alone when prices are recomputed.

        THE BUG THIS FIXES CHARGED NOTHING. A custom spring assembly priced at
        342.56 reached the payment step and became 0.00, and stayed 0.00 on
        every page after it - the customer could pay nothing for a made-to-order
        assembly.

        _recompute_prices runs whenever the pricelist changes, and the pricelist
        resolves late in checkout, when the partner is finally known. It calls
        _compute_price_unit with force_price_recomputation, which overrides even
        a manually written price, and the product deliberately lists at zero, so
        zero is what it computed. An ordinary quantity change never did this,
        which is why the cart looked right until the last screen.

        This hook exists for exactly this: Odoo documents it as excluding lines
        that should not be updated from the pricelist. These lines never came
        from a pricelist - the price is cone plus steel plus labour, times the
        markup - so there is nothing for a pricelist to say about them.
        """
        lines = super()._get_update_prices_lines()
        configured = self._door_configured_price_products()

        if not configured:
            return lines

        return lines - lines.filtered(lambda l: l.product_id in configured)

    # --- what counts as a prepared vertical track -----------------------------

    def _track_prep_is_prepared(self, line):
        """True when this cart line is a vertical track ordered PREPARED."""
        values = line.product_no_variant_attribute_value_ids

        return any(
            (v.name or "").strip().lower() == PREPARED for v in values
        )

    def _track_prep_door_height_feet(self, line):
        """The door height a cart line's track is for, in FEET."""
        return self._track_prep_height_from_name(
            line.product_id.display_name or "")

    def _track_prep_height_from_name(self, name):
        """The door height this track is for, in FEET, or 0 if unreadable.

        READ FROM THE PRODUCT NAME, because that is where it lives: the
        products are named like "CH-VT-2-2 Vertical Track 76-7 door height
        black", and the figure before "door height" is the door height in FEET.

        Name parsing is fragile and this is the fragile part of the feature, so
        it fails LOUDLY rather than guessing: a name this cannot read adds no
        parts and tells the customer to call, instead of silently shipping the
        wrong number of brackets. If the naming ever changes, the warning says
        so on the first order rather than after fifty.
        """
        # THE FOOT MARK IS THE POINT. The live products are named
        #
        #   [CH-VT-2"] 2" Vertical Track 76" - 7' Door Height Black
        #
        # so the figure before "Door Height" carries a PRIME - 7' - and the
        # first version of this pattern allowed only "ft", "foot" and "feet".
        # It read nothing, and every prepared track came back "we could not
        # read the door height". The inch marks are why this must not simply
        # grab the first number either: 2" and 76" both appear before it.
        #
        # Accepted: 7' Door Height, 7’ Door Height, 7 ft door height, 76-7 door
        # height, and a bare "8 door height".
        hit = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:'|\u2019|ft\.?|foot|feet)?\s*[-\u2013]?\s*door\s*height",
            name,
            re.I,
        )

        if not hit:
            return 0

        feet = float(hit.group(1))

        # A plausible door is between 5 and 20 feet. Anything else means the
        # number matched is not a door height, so treat it as unreadable.
        if not 5 <= feet <= 20:
            return 0

        return feet

    # THE JAMB BRACKETS ONE VERTICAL TRACK NEEDS, by door height.
    #
    # Taken from the owner's own garage door calculator, which carries the rule
    # as a table - andy0808al.github.io/garage-door-calculator, the JB array:
    #
    #     {min:0,   max:84,  j10:4, j12:4,  j14:4,  j16:null}
    #     {min:85,  max:96,  j10:4, j12:5,  j14:5,  j16:null}
    #     {min:97,  max:108, j10:4, j12:5,  j14:5,  j16:2}
    #     ... up to 192 inches
    #
    # PER TRACK, which is what a customer buys. The calculator calls these
    # numbers "per side" and doubles them for a door, because a door has two
    # vertical tracks - but the shop sells the tracks ONE AT A TIME, so the
    # per-side figure is the per-product figure and no doubling belongs here.
    # The owner states it plainly: "for one track its 4/4/4 for a 7 foot door",
    # and "when buying vertical tracks users are buying them individually not
    # in pairs".
    #
    # These quantities have now been wrong in both directions. They were first
    # read off a configurator result pasted into chat, which gave 6, 8 and 10
    # brackets by section count. Then the calculator's own table replaced that,
    # but doubled, on the belief that one product was the L & R pair - a belief
    # taken from the words "(L & R pair)" in a pasted track description, never
    # checked against what the product actually is. Doubled, every prepared
    # track shipped twice the brackets it needs.
    #
    # The table reaches 16 ft, which is what closes the 11 and 12 ft gap that
    # used to refuse those doors.
    BRACKET_MIX = (
        (0, 7, {"10": 4, "12": 4, "14": 4}),
        (8, 8, {"10": 4, "12": 5, "14": 5}),
        (9, 9, {"10": 4, "12": 5, "14": 5, "16": 2}),
        (10, 10, {"10": 4, "12": 5, "14": 5, "16": 4}),
        (11, 11, {"10": 4, "12": 5, "14": 5, "16": 6}),
        (12, 12, {"10": 4, "12": 6, "14": 6, "16": 6}),
        (13, 13, {"10": 4, "12": 6, "14": 6, "16": 8}),
        (14, 14, {"10": 4, "12": 6, "14": 8, "16": 8}),
        (15, 15, {"10": 4, "12": 6, "14": 8, "16": 10}),
        (16, 16, {"10": 4, "12": 6, "14": 10, "16": 10}),
    )

    # The catalogue part numbers, which are what the lookup keys on - a SKU is
    # a far steadier handle than a name someone may retitle.
    BRACKET_CODES = {
        "10": "ATL-610J10JBBR",
        "12": "ATL-614J12JBBR",
        "14": "ATL-616J14JBBR",
        "16": "ATL-616J16JBBR",
    }

    def _track_prep_bracket_mix(self, height_feet):
        """{size: quantity for ONE track} for this door, or {} if off the table.

        Off the table means off it. The table stops at 16 ft because the
        owner's calculator stops at 192 inches, and continuing the pattern past
        it would be inventing a trade rule rather than following one. A height
        it does not cover adds nothing and says to call.
        """
        for low, high, mix in self.BRACKET_MIX:
            if low <= height_feet <= high:
                return dict(mix)

        return {}

    # WHERE A BRACKET'S SIZE LIVES IN ITS NAME. Anchored on the hash the owner
    # writes, or the "J-" the catalogue uses, so the size is read from the
    # place it is declared rather than from the first number that happens to
    # appear - a pack count, a length, a price.
    _BRACKET_SIZE_ANCHORED = r"(?:#|\bJ-?)\s*-?\s*(\d+)"
    # A name with no hash at all - "Jamb Bracket 10 Black" - declares its size
    # with a bare number, so that is the fallback reading.
    _BRACKET_SIZE_BARE = r"(?<!\d)(\d+)(?!\d)"

    def _track_prep_declared_size(self, name):
        """The size this product's name claims to be, as an int, or None.

        ONE PRODUCT IS ONE SIZE, which is true of every bracket the owner
        stocks, and reading the name that way is what keeps a size-12 bracket
        named "Jamb Bracket # 12 Black (10 pack)" from answering to size 10.
        The alternative - asking "does 10 appear anywhere in this name" - says
        yes to that product, and the customer gets the wrong bracket.
        """
        for pattern in (self._BRACKET_SIZE_ANCHORED, self._BRACKET_SIZE_BARE):
            hit = re.search(pattern, name or "", re.I)

            if hit:
                return int(hit.group(1))

        return None

    def _track_prep_bracket_product(self, size, colour):
        """The jamb bracket of this size, in the track's finish.

        THE BRACKETS ARE COLOUR-MATCHED, like the flag angles. The owner stocks
        "Jamb Bracket # 10 Black" and "Jamb Bracket # 10 White" - eight
        products, four per finish - and only four of them belong on any given
        track.

        TOLERANT, BECAUSE AN EXACT NAME IS A TRAP. This once required the name
        to be exactly "Jamb Bracket # 10 Black". Any difference - "#10" without
        the space, a hyphen, a double space, a trailing one - matched nothing,
        and a bracket that is not found does not fail by itself: _track_prep_sync
        abandons the WHOLE preparation, removing every part and adding none. So
        one space in one product name empties the order of brackets AND flag
        angles, leaving the track by itself. That is a great deal of consequence
        to hang on a space.

        An earlier version before that searched only the catalogue part numbers
        and the "J-10 Jamb Bracket" names from garage_door_supply's data. The
        live site has neither, so every prepared track was refused with a list
        of three part numbers that exist nowhere.
        """
        Product = self.env["product.product"].sudo()

        # 1. The names the owner actually stocks, and the obvious variant of
        #    them. First, so the ordinary case never depends on the scan below
        #    and always answers with the same product.
        for pattern in ("Jamb Bracket # %s %s", "Jamb Bracket #%s %s"):
            found = Product.search(
                [("name", "=ilike", pattern % (size, colour))], limit=1
            )

            if found:
                return found

        # 2. Anything that reads like a jamb bracket of this size in this
        #    finish. Ordered by name so a catalogue holding two candidates
        #    resolves the same way on every order rather than by chance.
        wanted = int(size)

        for product in Product.search([("name", "ilike", "jamb")], order="name"):
            name = product.name or ""

            if not re.search(r"\bbracket\b", name, re.I):
                continue

            # A black track must never be given a white bracket, so the finish
            # is required as a WHOLE WORD - Black does not match Blackened.
            if not re.search(r"\b%s\b" % re.escape(colour), name, re.I):
                continue

            if self._track_prep_declared_size(name) == wanted:
                return product

        # 3. The catalogue part numbers, for a database carrying
        #    garage_door_supply's data instead of the owner's own products.
        code = self.BRACKET_CODES.get(size)

        if code:
            found = Product.search([("default_code", "=", code)], limit=1)

            if found:
                return found

        return Product.search(
            [("name", "=ilike", "J-%s Jamb Bracket" % size)], limit=1
        )

    def _track_prep_bracket_name(self, size, colour):
        """What the lookup wanted, phrased so a person can search for it."""
        return "Jamb Bracket # %s %s" % (size, colour)

    # ONE PER TRACK. A flag angle sits at the top of a single vertical track,
    # so a door takes two and a track takes one - which is what the owner asked
    # for in the first place: "jamb brackets, just 1 flag angle". The owner's
    # own kit configurator returns "2 flag angles" for a 9' x 7' DOOR, the same
    # answer counted the other way round.
    #
    # This was 2 for as long as the bracket table was doubled, on the same
    # mistaken belief that one product was the L & R pair.
    FLAG_ANGLES_PER_TRACK = 1

    # The finishes a track and its flag angle come in. Matched as whole words so
    # a track that merely mentions a colour elsewhere in its name is not caught.
    COLOURS = ("Black", "White")

    def _track_prep_colour(self, line):
        """The finish of a cart line's track."""
        return self._track_prep_colour_from_name(
            line.product_id.display_name or "")

    def _track_prep_colour_from_name(self, name):
        """The track's finish, as the flag angle products spell it, or None.

        The flag angle has to MATCH THE TRACK: the products are "Flag Angle
        Black" and "Flag Angle White", so a black track must not ship a white
        angle. There is no sensible default here - shipping the wrong colour is
        a return - so an unrecognised finish adds nothing and says so, the same
        as an unreadable height.
        """
        for colour in self.COLOURS:
            if re.search(r"\b%s\b" % colour, name or "", re.I):
                return colour

        return None

    def _track_prep_configured_part(self, key):
        """The product named in the settings for this role, or an empty set."""
        ref = self.env["ir.config_parameter"].sudo().get_param(
            "spring_engineering.track_prep_%s_product_id" % key
        )

        if not ref:
            return self.env["product.product"]

        try:
            return self.env["product.product"].sudo().browse(int(ref)).exists()
        except (TypeError, ValueError):
            return self.env["product.product"]

    def _track_prep_flag_product(self, line):
        """The flag angle matching a cart line's track."""
        return self._track_prep_flag_for_colour(self._track_prep_colour(line))

    def _track_prep_flag_for_colour(self, colour):
        """The flag angle in the track's own finish.

        Looked up BY NAME rather than configured, because there is one per
        colour and the right one depends on the track rather than on a setting.
        The setting stays as a fallback for a track whose finish is a colour
        these products do not cover.
        """
        if colour:
            Product = self.env["product.product"].sudo()
            exact = Product.search(
                [("name", "=ilike", "Flag Angle %s" % colour)], limit=1
            )

            if exact:
                return exact

            # SAME TOLERANCE AS THE BRACKETS, for the same reason: a flag angle
            # that is not found takes the whole preparation down with it, so
            # "Flag Angle - Black" costing the customer every bracket on the
            # order is not a trade the strict lookup was ever worth making.
            for product in Product.search([("name", "ilike", "flag")], order="name"):
                name = product.name or ""

                if re.search(r"\bangle\b", name, re.I) \
                        and re.search(r"\b%s\b" % re.escape(colour), name, re.I):
                    return product

        return self._track_prep_configured_part("flag")

    # --- keeping the parts in step with the track -----------------------------

    def _track_prep_requirements(self, product, qty=1.0):
        """({role: (part, quantity)}, warning): what preparing this track needs.

        ONE PLACE WORKS IT OUT, so the price the shop page shows and the lines
        the cart books cannot disagree. The cart calls this to create the
        lines; product_template calls it to price the Prepared option before
        anything is in a cart.

        A warning means nothing is added - every part or none, because a
        prepared track missing its brackets is not a thing the owner sells.
        """
        height_feet = self._track_prep_height_from_name(
            product.display_name or "")

        if not height_feet:
            return {}, _(
                "We could not read the door height from “%s”, so the jamb"
                " brackets and flag angle were not added. Please call us and we"
                " will prepare it for you.",
                product.display_name,
            )

        colour = self._track_prep_colour_from_name(product.display_name or "")

        if not colour:
            return {}, _(
                "We could not tell what finish “%s” is, so the flag angle was"
                " not added - it has to match the track. Please call us and we"
                " will prepare it for you.",
                product.display_name,
            )

        mix = self._track_prep_bracket_mix(height_feet)

        if not mix:
            return {}, _(
                "A %s ft door is outside the sizes we prepare tracks for, so"
                " the parts were not added. Please call us and we will prepare"
                " it for you.",
                ("%g" % height_feet),
            )

        wanted = {
            "flag": (
                self._track_prep_flag_for_colour(colour),
                self.FLAG_ANGLES_PER_TRACK * qty,
            ),
        }

        for size, count in mix.items():
            wanted["jamb_%s" % size] = (
                self._track_prep_bracket_product(size, colour),
                count * qty,
            )

        missing = [k for k, (p, _q) in wanted.items() if not p]

        if missing:
            # NAME WHAT IS MISSING, THE WAY THE OWNER NAMES IT. The first
            # version of this said "the parts are not configured yet", which
            # sent someone looking for a setting that does not exist. The
            # second named the catalogue PART NUMBERS - better, but they were
            # the numbers from a module the live site does not have, so the
            # message listed three codes that exist nowhere. A product name is
            # something that can actually be searched for in the back end.
            wants = ", ".join(sorted(
                self._track_prep_bracket_name(key.replace("jamb_", ""), colour)
                if key.startswith("jamb_")
                else "Flag Angle %s" % colour
                for key in missing
            ))

            return {}, _(
                "We are missing a part needed to prepare this track (%s), so it"
                " was not added. Please call us and we will prepare it for you.",
                wants,
            )

        return wanted, None

    def _track_prep_sync(self, line):
        """Create, update or remove the parts belonging to one track line."""
        self.ensure_one()

        existing = self.order_line.filtered(lambda l: l.track_prep_parent_id == line)

        if not line.exists() or not self._track_prep_is_prepared(line):
            existing.unlink()
            return None

        wanted, warning = self._track_prep_requirements(
            line.product_id, line.product_uom_qty)

        if warning:
            existing.unlink()

            return warning

        for role, (product, qty) in wanted.items():
            part = existing.filtered(lambda l: l.track_prep_role == role)[:1]

            if part:
                if part.product_uom_qty != qty:
                    part.product_uom_qty = qty
                continue

            self.env["sale.order.line"].create({
                "order_id": self.id,
                "product_id": product.id,
                "product_uom_qty": qty,
                "track_prep_parent_id": line.id,
                "track_prep_role": role,
            })

        # Anything linked to this track that is no longer one of the two roles -
        # left over from an earlier version of this rule - goes.
        existing.filtered(lambda l: l.track_prep_role not in wanted).unlink()

        return None

    # --- hooks ----------------------------------------------------------------

    def _cart_add(self, product_id, quantity=1.0, *, uom_id=None, **kwargs):
        """Add a track, then add what preparing it needs."""
        result = super()._cart_add(product_id, quantity, uom_id=uom_id, **kwargs)
        line = self.env["sale.order.line"].browse(result.get("line_id"))

        if line.exists():
            warning = self._track_prep_sync(line)

            if warning:
                result["warning"] = "\n".join(filter(None, [result.get("warning"), warning]))

        # AFTER the track's own parts, because those parts are brackets and
        # the fasteners are counted from them.
        warning = self._fastener_sync()

        if warning:
            result["warning"] = "\n".join(filter(None, [result.get("warning"), warning]))

        return result

    def _cart_update_line_quantity(self, line_id, quantity, **kwargs):
        """Follow the track's quantity, and never let a part be edited alone.

        A customer who sets the track to 3 gets three doors' worth of brackets.
        A customer who edits the BRACKET line directly is redirected to the
        track, because a prepared track with the wrong number of brackets is
        not a thing the owner sells - and silently accepting the edit would
        ship exactly that.
        """
        line = self.env["sale.order.line"].browse(line_id)

        # A FASTENER IS NOT OPTIONAL, so it is not editable on its own either.
        # The cart owes one per bracket; changing that number by hand would
        # ship brackets nobody can fit.
        if line.exists() and line.track_prep_role in self.FASTENER_ROLES:
            self._fastener_sync()

            return self._fastener_answer(line_id, line)

        if line.exists() and line.track_prep_parent_id:
            parent = line.track_prep_parent_id

            if quantity <= 0:
                # Removing a part means the track is no longer prepared.
                result = super()._cart_update_line_quantity(parent.id, 0, **kwargs)
            else:
                self._track_prep_sync(parent)
                result = self._fastener_answer(line_id, line)

            # EVERY WAY OUT OF THIS METHOD COUNTS THE BRACKETS AGAIN. These two
            # returned without doing so, and that is what left a cart holding
            # nothing but studs and nuts: taking a prepared track away by
            # removing one of ITS OWN parts goes down this branch, the track
            # and its brackets went, and the fasteners stayed behind with the
            # quantity the brackets used to have.
            self._fastener_sync()

            return result

        result = super()._cart_update_line_quantity(line_id, quantity, **kwargs)

        if line.exists():
            self._track_prep_sync(line)

        self._fastener_sync()

        return result

    def _fastener_answer(self, line_id, line):
        """What to tell the page about a line the sync may have just removed.

        READ AFTER THE SYNC, NOT BEFORE. Asking a deleted record for its
        quantity is what produced "Missing Record. Record does not exist or has
        been deleted" when somebody pressed Remove on the last stud in a cart
        with no brackets left: the rule quite correctly took the line away, and
        then this went looking for it.
        """
        line = line.exists()

        return {
            "quantity": line.product_uom_qty if line else 0,
            "line_id": line_id,
        }

    # --- what every jamb bracket is fitted with -------------------------------
    #
    # A BRACKET DOES NOT GO ON THE DOOR BY ITSELF. Each one takes a knurled
    # stud and a flange nut, so the cart owes one of each per bracket - four
    # brackets, four studs, four nuts.
    #
    # WRITTEN AS A RULE ABOUT THE CART, not as a step in the two places a
    # bracket can arrive. It can come from the shop, bought on its own, or
    # from a prepared track, which adds a graduated mix of sizes by itself -
    # and the quantity of either can change afterwards. Counting what the cart
    # holds and making the fasteners match is one rule that cannot disagree
    # with itself; a step bolted onto each path is two rules that can.
    FASTENER_ROLES = FASTENER_ROLES

    # THE OWNER'S OWN SPELLINGS FIRST - "1/4 X 3/4 KNURLEL STUD 18-8" and
    # "Flage Nuts 1/4 20" - then a tolerant read, because a name typed twice is
    # a name typed differently. The patterns allow the spelling with the n and
    # the one without, which is the difference between flange and flage.
    FASTENER_NAMES = {
        "stud": "1/4 X 3/4 KNURLEL STUD 18-8",
        "nut": "Flage Nuts 1/4 20",
    }
    FASTENER_PATTERNS = {
        "stud": (r"\bstud\b", r"knurl"),
        "nut": (r"\bnuts?\b", r"\bflan?ge\b"),
    }
    FASTENER_LABELS = {"stud": "knurled stud", "nut": "flange nut"}

    def _fastener_is_bracket(self, line):
        """Is this cart line a jamb bracket, however it got here?"""
        product = line.product_id

        if not product:
            return False

        if product.default_code and product.default_code in self.BRACKET_CODES.values():
            return True

        name = product.display_name or ""

        return bool(
            re.search(r"\bjamb\b", name, re.I)
            and re.search(r"\bbracket\b", name, re.I)
        )

    def _fastener_product(self, role):
        """The stud or the nut, found the way the brackets are found."""
        Product = self.env["product.product"].sudo()
        exact = Product.search(
            [("name", "=ilike", self.FASTENER_NAMES[role])], limit=1)

        if exact:
            return exact

        first, second = self.FASTENER_PATTERNS[role]

        for product in Product.search([("name", "ilike", "/4")], order="name"):
            name = product.name or ""

            if re.search(first, name, re.I) and re.search(second, name, re.I):
                return product

        # The same settings fallback the flag angle has, for a catalogue that
        # names these something this cannot read.
        return self._track_prep_configured_part(role)

    def _fastener_count_in_the_header(self):
        """Tell the navbar what the cart now holds.

        THE BADGE IS A SESSION VALUE, NOT A QUERY. website_sale caches
        cart_quantity in the session - _verify_cart_after_update writes it, and
        a page rendered afterwards reads it rather than counting the lines - so
        changing lines underneath it leaves the number stale. That is why the
        header kept saying 24 over an empty cart until something else was
        added: the next add wrote the figure again.

        This runs after the fasteners have moved, which is after the update
        that triggered it has already written its own.
        """
        if request:
            request.session["website_sale_cart_quantity"] = self.cart_quantity

    def _fastener_sync(self):
        """One stud and one nut for every jamb bracket, under each bracket.

        PER BRACKET LINE, not per cart. They used to be one stud line and one
        nut line counted across everything, which was simpler and wrong in two
        ways the owner asked about: the cart could not show them under the
        bracket they belong to, and a prepared track - which brings three
        bracket lines of different sizes - had no way to say which pair went
        with which. Hanging each pair off its own bracket also means the link
        deletes them: track_prep_parent_id cascades, so taking a bracket out
        takes its fasteners with it.
        """
        self.ensure_one()
        brackets = self.order_line.filtered(self._fastener_is_bracket)
        changed = False

        # Anything left pointing at a line that is no longer a bracket - or at
        # nothing at all, which is what the cart-wide version left behind.
        orphans = self.order_line.filtered(
            lambda line: line.track_prep_role in self.FASTENER_ROLES
            and line.track_prep_parent_id not in brackets)

        if orphans:
            orphans.unlink()
            changed = True

        missing = []

        for bracket in brackets:
            for role in self.FASTENER_ROLES:
                product = self._fastener_product(role)
                line = bracket.aa_included_line_ids.filtered(
                    lambda l, role=role: l.track_prep_role == role)[:1]

                if not product:
                    # NAMED, NOT COUNTED. "A part is missing" sends somebody
                    # looking through a catalogue; the name can be searched
                    # for. Said once however many brackets are in the cart.
                    label = "%s (%s)" % (
                        self.FASTENER_LABELS[role], self.FASTENER_NAMES[role])

                    if label not in missing:
                        missing.append(label)

                    if line:
                        line.unlink()
                        changed = True

                    continue

                if line:
                    if line.product_uom_qty != bracket.product_uom_qty:
                        line.product_uom_qty = bracket.product_uom_qty
                        changed = True

                    continue

                self.env["sale.order.line"].create({
                    "order_id": self.id,
                    "product_id": product.id,
                    "product_uom_qty": bracket.product_uom_qty,
                    "track_prep_parent_id": bracket.id,
                    "track_prep_role": role,
                })
                changed = True

        if changed:
            self._fastener_count_in_the_header()

        if missing:
            return _(
                "We are missing a part that goes with the jamb brackets (%s),"
                " so it was not added. Please call us and we will send it with"
                " them.",
                ", ".join(missing),
            )

        return None
