# AA Impact Garage Door Supply — project facts

Standing decisions for this repository. These are the user's own statements about
how the business works, not inferences. **Read this before changing behaviour.**

## The spring calculator (`spring_engineering`)

### Only ONE Duplex spring ID is used: `3 3/4" inside 6"`

Stated by the owner, 2026-10-07: *"we are only using 3 3/4\" inside 6\" spring id,
please permanently remember that."*

This is why the dropdown offers that pair alone. Three others used to be listed and
**all three gave wrong answers**, because every one of the 8,464 reference readings
behind the model is for `3 3/4" inside 6"`:

| option | what the reference said | what we said |
|---|---|---|
| `2 5/8" inside 5 1/4"` | 0.2625/0.1875, 15" / 16" | 0.2625/0.1875, **17" / 18"** |
| `3 1/2" inside 5 1/2" (Raynor)` | **0.25/0.207**, 15" / 16" | 0.2625/0.1875, **17" / 18"** |
| `3 3/8" inside 5 7/8" (Overhead)` | never measured | aliased to 2 5/8 inside 5 1/4 |

Two inches of length and the wrong wire on the Raynor pair - and the aliases that
mapped Raynor and Overhead onto `2 5/8" inside 5 1/4"` were simply wrong, which the
reference showed by giving a different wire size for the same door.

**Do not re-add a pair to the dropdown without calibrating it first.** Calibrating
one took thousands of reference readings; see `spring_engineering/dev/README.md`.
Offering a size the model cannot compute is worse than not offering it.

### DUPLEX IS CALCULATED BUT NO LONGER SOLD (owner, 2026-10-28)

*"for duplex springs we will leave the option there for people who want to use
it, but customers will no longer be able to add duplex springs to the cart,
instead give them a message on the page that will say something like we do not
currently manufacture custom duplex springs. currently there is a message for
going under our available wire size, you can replace that with the duplex
message only for when duplex is selected."*

**THE CALCULATOR IS UNTOUCHED.** The option stays in the dropdown, the pair is
still worked out, the figures are still drawn - he asked for that in the same
breath, and somebody sizing a duplex they already own is exactly who the page
is for. What goes is the SALE.

**THE LOCK IS `UNBUILDABLE_ASSEMBLIES` IN `controllers/main.py`**, checked in
`quote_assembly` - not in the route, because the calculator's own Add to Cart
is not the only way in: the dealer Quick Order prices springs through the same
function, and a spring the shop cannot make it cannot make for a dealer
either. The dealer page shows it as a note against the line. It is a separate
tuple from `ASSEMBLIES`, which says what the code can WORK OUT, so turning
duplex back on is deleting one word.

The page's Contact Us button is the courtesy; the route is public and takes a
posted specification, so a hidden button stops nobody.

**THE MESSAGE REPLACES THE WIRE WARNING, it does not stack on it** - his
words. A duplex pair often lands on a wire we do not stock anyway, and two
reasons we cannot sell it is one more than anybody needs. `duplexNotMade`,
`showWireStockWarning` (which is `!duplexNotMade && unstockedWires.length`)
and `cannotBeSold` are the three getters; the template and the wire-stock
tests read those names.

**EVERY FIXTURE IN THE REPOSITORY QUOTED A DUPLEX**, because it was the
richest spec to write: `spring_engineering` test_add_to_cart (the default
`_spec()`), test_cart_cost, test_checkout_price, and `aa_shop_floor`
test_hardware_card. All now send a Single. Note `springs: 2` is TWO SPRINGS ON
THE DOOR - a left and a right - and `springsSpec` is the NEST; only the nest
is withdrawn.

**OLD DUPLEX ORDERS MUST STILL PRINT.** His database holds them and they are
still on the floor, so the Hardware card's outer/inner rows are still tested -
against an order built with the ban lifted by `patch.object`, which is now the
only way to make one.

**A PRE-EXISTING FAILURE, NOT THIS: `spring_engineering` test_bracket_fasteners
has 5 failures and 2 errors on a clean tree** (checked by stashing). Nothing
to do with duplex; it is about prepared-track brackets and fasteners.

### THE SHOP CARD AND THE PRODUCT PAGE SHOWED DIFFERENT PRICES (owner, 2026-10-28)

*"kit prices aren't matching, for example the aa-1200 hardware kit says 254.39
when you first see it on the shop page, but when you enter its product page it
says 293.97 on its default values."*

**ODOO'S OWN DOING, and two methods that were never asked the same question.**
The SHOP GRID calls `_get_sales_prices`, which prices the TEMPLATE -
`pricelist._compute_price_rule(template, 1)` - with NO COMBINATION, so not one
attribute extra is in it. The PRODUCT PAGE calls `_get_combination_info`,
which with no combination picks `_get_first_possible_combination()` and prices
THAT VARIANT. 293.97 - 254.39 = **39.58**, which is what his AA-1200's default
values add.

**IT IS NOT ONE KIT.** Since the merge of 2026-10-21 nearly every family here
is priced as "the product's price plus an extra per size", so the grid has
been under-stating hinges, shafts, brackets and the rest too. A kit only made
it visible by putting forty dollars between the two screens.

`spring_engineering/models/shop_grid_price.py` overrides `_get_sales_prices`
to ask `_get_combination_info` for the very answer the page will give.
**NOT BY ARITHMETIC**: the number Odoo worked out has already been through the
pricelist, the fiscal position and the tax display setting, and an extra is
none of those - on a tax-inclusive shop, adding it would land outside the tax.
It only runs where `_aa_has_priced_attributes()` is true, which is a field
read, so the rest of the catalogue pays nothing.

**THE PAGE IS THE ONE THAT IS RIGHT.** The card could have said "from $254.39"
instead, which is Odoo's reading of that number - but the first price the shop
shows should not be one the customer can never pay.

**`_get_sales_prices` CANNOT BE CALLED UNDER `MockRequest` either** - it reads
`request.pricelist` and immediately subscripts it, and the mock is not
subscriptable. Same trap as `_get_combination_info`. The tests FETCH both
pages, which is also where he read the two numbers.

**AND THE DEV DATABASE HAS A DEMO PRICELIST taking 10% off everything**, so no
absolute figure asserted there means anything. The fault is a DIFFERENCE
between two screens and that survives any pricelist, so the tests compare the
two rather than measuring either. Fixtures also need UNIQUE NAMES: the shop is
searched by name to get a grid of one card, and two fixtures called the same
thing put two cards there, the first answering for both.

### Only the three visible Single spring IDs are used

Stated earlier by the owner: *"we are not using all of the single spring id's only
the ones that are visible to the user"* - which is `2 5/8"`, `3 3/4"` and `5 1/4"`.
All three agree with the reference exactly on the case checked.

### 6" is priced as 5 1/4"

Stated by the owner: *"6\" is the same as 5 1/4\""* for cone pricing.

## Pricing

### A 5 1/4" spring takes a plastic filler

Stated by the owner, 2026-10-08: one filler **per spring**, cut to that spring's
own length - *"a 4 foot spring would need 4 feet of filler"*. Quoted as $19.44 for
6 ft and $22.68 for 7 ft, which are both exactly **$3.24 a foot**, so the rate is
what is stored and the two quotes are the same price twice.

It is a separate product (`product_custom_filler`), **not published**, so it cannot
be bought on its own - it reaches a cart only when the calculator adds a spring
whose ID calls for one. The order line's quantity is FEET.

Charged at cost, with no markup, the same as the cones (owner, 2026-10-16).

### The steel rate is an ordinary setting

Editable in Website > Configuration > Settings like the markup and the labour
charge, but not secret - it is a commodity price. Default $1.46/lb, in
`spring_engineering/pricing.py`.

### How the pieces fit together (owner, 2026-10-16)

- The per-pound setting ("Spring sell price per pound", key
  `spring_engineering.steel_per_lb`) is the SALE price: the owner enters cost +
  labour (and his margin) per pound. It is NOT marked up.
- Cones and the plastic filler are added on top AT COST, with no markup.
  `_markup_factor()` returns 1; the "Cones & filler markup" setting was removed
  from Settings (the old `spring_engineering.markup_percent` row is ignored).
- There is no separate labour charge; `_labor_flat()` returns 0.
- No dealer margin on springs: `aa_dealer_orders` `_spring_factor()` returns None,
  so a spring costs every customer the same.
- Cone and filler COSTS live in `spring_engineering/pricing.py`, server side.

### Spring steel COSTS $0.81 a pound (owner, 2026-10-21)

A SECOND FIGURE, not a division of the sell rate. "Spring sell price per pound"
($1.46) has the winding labour and the margin inside it, so no arithmetic on it
can recover a cost. The cost is its own setting next to it in Website >
Configuration > Settings - "Spring steel cost per pound", key
`spring_engineering.steel_cost_per_lb`, default in `pricing.py` as
`STEEL_COST_PER_LB` - because steel moves and the owner changes it himself.

**Nothing a customer sees is priced from it.** Its only use is the staff-only
cost line on the cart (`sale.order._aa_cart_cost`), which costs a custom spring
the way the quote prices it: the same weights off the same stored
`spring_spec_json`, cones at the `pricing.py` cost, and this rate in place of
the sell rate. Left at nothing, a spring is reported as "no cost set" rather
than counted at the price of its cones alone - which would look like a costed
line and be out by a factor of ten.

### The cart's cost line is for employees only

`_aa_cart_cost()` returns None for anyone who is not an internal user, so a
customer renders the row as nothing at all. The `t-if` in
`views/cart_cost.xml` is the second lock, not the only one: that template is
reachable from the website editor and the cost of goods is not a number to
guard with an xpath. Keep the decision in Python.

### Hardware station

Each hardware kit line gets a "Pack hardware kit" MO (kit, color, panels, rollers,
drum, track, lift, door size, weight) and each prepared lift cable pair gets a
"Cut lift cables" MO (size, cut length = the pair's reel feet / 2, sleeve, thimble,
stop per cable). The station BoMs are NORMAL, template-level, with no components:
the delivery still explodes the kits' and cables' own phantom BoMs.

## Customer emails (`work_order_sheet`)

All four the customer can receive are in one file,
`work_order_sheet/data/customer_emails.xml` (owner, 2026-10-19: "review every
email the customer receives" should be one thing to read): the order
confirmation, the invoice, "ready to collect" and the cancellation. Two of the
four are **Odoo's own records re-written in place**, so they cannot be
abandoned - dropping the override brings Odoo's generic wall of table back
rather than silence. `_aa_own_customer_emails` clears the `noupdate` flag on
them, without which the bodies below do nothing at all.

### THE ORDER-CONFIRMED EMAIL IS NOT SENT FOR AN ORDER ALREADY PAID

Owner, 2026-10-27, having placed S00070: *"when making an order i got 2 emails
about the invoice ... i need you to make it so that email is no longer sent"* -
the invoice being the one to keep.

He is right that they duplicate. A website order is paid at checkout, so Odoo
confirms it and raises the invoice in the same breath, and the customer gets a
confirmation carrying the quotation PDF and an invoice carrying the invoice
PDF, moments apart.

**BUT IT IS NOT ONLY A WEBSITE EMAIL.** A dealer placing a Quick Order charged
to account gets it too, and that order raises NO invoice at the time - so for
a dealer it is the only acknowledgement until "ready to collect" days later.
Asked, the owner chose to stop it **only where the invoice follows**.

So `_send_order_confirmation_mail` in
`work_order_sheet/models/order_confirmation_email.py` asks **"has this order
already been paid"** - a transaction in `done` or `authorized` - and not "is
this the website". A dealer's on-account transaction sits at `pending` for
ever, and a back office order typed by hand has no transaction, so both keep
their confirmation. `super()` is still called, on a narrowed recordset, so
nothing else that hooks the method is lost.

### THE DEALER'S PO NUMBER IS ON THE WORK ORDER (owner, 2026-10-29)

*"in dealer quick order there is a po number that users can input, however
this number doesnt show up at all in the work order, can you fix that?"*

**NOTHING HAD TO BE CAPTURED.** The Quick Order already stores it in Odoo's
own `client_order_ref` on the sale order (`aa_dealer_orders/controllers.py`),
where it is **REQUIRED** - a dealer cannot submit without one. It was simply
never printed.

**THE SHEET IS A TRANSFER, NOT AN ORDER**, which is the whole reason it never
appeared: every field on the Work Order Sheet comes off `stock.picking`, and
the PO is two records away. `_work_order_po_number()` crosses that with
`_work_order_sale_order()`, which also finds the order of a transfer carrying
nothing but a Source Document - a route-made one has no `sale_id`.

It prints in THREE places: the cover, in the shop's own red because on a
counter full of paper it is the one number somebody is hunting for; **every
station page**, for the same reason the door's size is repeated, since the
sheet gets split up and handed out; and the **delivery confirmation**, which
is the form that goes back with the dealer and what he reconciles against.
One line each to remove.

An order with NO reference - a website order, or one typed in the back
office - prints nothing rather than an empty label, which would read as a
number somebody forgot to write down.

**`t-set` AT ARTICLE SCOPE, NOT INSIDE THE COVER.** The station pages are
SIBLINGS of the cover, so a `t-set` buried in one of them is in scope for the
others by luck rather than by rule; `po` is set beside `sections`, `door` and
`lines` where the template already sets the sheet-wide values.

**AND THEN ON THE SCREEN** - owner, an hour later: *"can you make the po
visible on the work order page"*.

`aa_po_number` on `stock.picking`, **STORED**, which is the whole point: a
method can SHOW a number but not FIND one, and finding is what this is for -
a dealer telephones about PO-44821 and nobody here knows which of ours that
is. It is on the FORM beside the Source Document (they are the same fact told
twice, his name for the order and ours), as a COLUMN on the Work Orders list,
and in the SEARCH box.

**THE COLUMN IS NOT `optional`**, the same call as the Dispatch pickup
column: `optional="show"` is shown only to somebody who has never touched
that list's column chooser, and he has touched this one - it already carries
Dispatched and the station badges.

**NO MIGRATION.** Odoo backfills a stored computed column when it adds it,
and that was PROVED rather than assumed: blank the column by hand, call
`env.add_to_compute(field, all_records)` - which is Odoo's own mechanism -
and the value comes back.

**ONE GAP, WRITTEN DOWN RATHER THAN PAPERED OVER**: a transfer carrying only
a Source Document is matched to its order BY NAME, and no `depends` can reach
back through a string, so changing the reference on such an order does not
follow until the transfer is touched. Every dealer order has a real
`sale_id`; this is the route-made case only.

### DISPATCHED FOR THE RECORD, WITHOUT USING ANY STOCK (owner, 2026-10-29)

He asked first whether it was possible - *"is there a way to mark an order as
sent without using up inventory?"* - and then for it, in the **Actions menu**
of the Dispatch list with thirty transfers ticked, carrying his own warning:
*"this is only for orders that used no actual inventory and is only to be
used for records or testing, not for real orders."*

**ODOO WILL NOT LET A TRANSFER BE DONE WHILE MOVING NOTHING**, and both
obvious ways round it were MEASURED before anything was written:

- **All quantities at nought** (with `skip_sanity_check`, which is a
  supported context key): `_action_done` CANCELS a zero-quantity move, so the
  transfer ends up **Cancelled**, not dispatched. Stock untouched, but it is
  not "sent".
- **Dispatching with an empty rack**: Odoo does not block at all - it takes
  the quant **negative** (-5 in the rehearsal). That is the opposite of what
  he asked for.

**SO EVERY LINE IS DELIVERED TO WHERE IT CAME FROM.** `line.location_dest_id
= line.location_id`, at the full quantity, through Odoo's own
`button_validate` - so the transfer is genuinely Done and the order genuinely
reads as delivered - and because the source and destination are the same
quant, the decrement and the increment are the same number. Measured: 45 on
hand before, 45 after, 50 in the building either way.

**THE CHATTER SAYS WHAT HAPPENED.** A transfer reading Done while the shelf
never moved is a lie unless somebody wrote it down, and whoever opens that
order in six months needs to know why its stock never went anywhere.

**STOCK MANAGERS ONLY** (`group_ids` on the server action). On a real order
this silently breaks the count of everything on it, which is what his own
warning says; the group makes the warning true.

**ONE AWKWARD TRANSFER DOES NOT ABANDON THE OTHER TWENTY-NINE** - he had
thirty selected. Each is tried on its own and the refusals are named back.

Two Odoo 19 details that each cost a load: **`ir.actions.server` has
`group_ids`, not `groups_id`** (the module would not install), and **a
`alert-heading` class inside an alert trips the view checker's accessibility
rule** - every `alert-*` class wants an alert role, which a heading cannot
carry.

### ONE CANCELLATION EMAIL PER ORDER, WHOEVER CANCELS IT

Owner, 2026-10-27: *"i need you to make it so the user gets an email when
their order is cancelled, specifically when it gets cancelled on
manufacturing, i dont want to send multiple emails if i also have to cancel it
again in the sales module or some other module that isn't manufacturing."*

So the rule is not "send from manufacturing" - it is **send once per order,
from whichever place gets there first**. `aa_cancel_email_sent` on sale.order
is the stamp, written the moment the mail goes, and every path asks the same
`_aa_send_cancellation_email()`. A flag rather than searching the chatter,
because a message that failed to send still leaves a message.

Three ways in, all in `work_order_sheet/models/order_cancelled_email.py`:
`sale.order._action_cancel` (Sales, and everything that is not a job), the
cancel-and-refund wizard, and `mrp.production.action_cancel` - which also
catches the Shop Floor, since cancelling a work order there settles its
station job through `action_cancel` too.

**AN ORDER IS NOT ONE JOB.** Confirming it raises a Springs job, a Pack
hardware kit job and a Cut lift cables job, and Odoo's route may add a
prepared track job. Asked whether the email should go on the first job
cancelled or the last, the owner chose **when nothing is left being made**. A
job already DONE does not count as nothing: something was built, so that case
stays quiet and is left to a Sales cancellation.

Jobs DELETED rather than cancelled send nothing - deletion is cleanup, and the
Shop-floor cleanup screen deletes jobs whose order has gone, where there is
nobody to email.

**THE WIZARD HOLDS THE EMAIL BACK.** It cancels the shop floor jobs FIRST and
refunds afterwards, so without `aa_hold_cancel_email` on its first three steps
the "$X refunded" email would go out before the refund had been attempted, and
be a promise if it then failed.

**Orders already cancelled were stamped by the 19.0.1.40.0 migration.** His
database has orders cancelled weeks ago whose jobs still stand open, and the
first use of the cleanup screen after this deployed would otherwise have told
a dozen customers that a September order is cancelled.

## Shop add-ons under a kit or a spring (`aa_shop_addons`)

Owner, 2026-10-27: *"On every kit and spring page, show the matching add-ons
(cones, cables, tracks, trims) below the product. Done when: each kit shows
its correct add-ons."*

**WHAT MAKES ONE CORRECT IS HIS CALL, NOT A RULE.** A kit knows its series and
its panel count and nothing else; what picks one cable out of twelve is the
door height and the drum, and what picks one track is the height, the track
size and the colour. Asked whether to guess, show the families, or choose
himself, he chose to choose - so the list is **Odoo's own Alternative
Products field** on each of the twelve kits. Right by definition.

**IT IS ON THE SALES TAB UNDER "UPSELL & CROSS-SELL"**, and it is hidden
entirely unless the product has `sale_ok` ticked. I first wrote "Sales tab >
eCommerce", which is not a section that exists, and he went looking for it on
Prod and could not find it. The field is ODOO'S OWN and has always been there -
nothing of ours has to be deployed before he can fill it in.

**ONE BOX IN THAT GROUP, NOT THREE** (owner, 2026-10-27: *"we only want the
alternative products choice, you can get rid of the other two, that being
optional products and accesory products"*). This first used Accessory
Products; Alternative is the better fit anyway, because Odoo's own help for it
says those products "show up on the product page", which is where these go -
Accessory feeds the CART and Optional feeds a QUOTATION. The other two are
HIDDEN, not deleted, by `views/product_views.xml`; whatever is in them still
works for anything that reads it. Alternative Products is also a Many2many of
TEMPLATES rather than variants, so one entry covers a track with all twenty
combinations behind it.

### THEN HE ASKED FOR IT WITHOUT THE TYPING (owner, 2026-10-27)

*"could you automate a system that will recommend additional products the same
way that the alternative product thing works. this way i wont have to
individually go into every products page to seach which products i should
recommend alongside it."*

**HE HAD ALREADY ANSWERED IT, AT THE COUNTER, ALL YEAR.** "Which cable should
go with this kit" is an engineering question nothing here can answer - that is
still true and is why there is no rule. But **"which cable do people who buy
this kit buy" is a COUNTING question**, and the answer is in `sale_order_line`.
So `aa.addon.suggestion` counts, every night, the products that appear on the
SAME orders as each kit and the spring. Nothing is guessed: it cannot
recommend something nobody has bought alongside, which is exactly why it can
be trusted with a page nobody has reviewed.

**THREE TIERS, IN THIS ORDER**: what HE picked (unchanged, still right by
definition), then what his ORDERS say, then the families. His pick is never
overruled by a count.

Four things the count refuses to be fooled by, each of which would otherwise
put a product on the website on the strength of nothing: a QUOTATION nobody
accepted (`sale` and `done` only), a CANCELLED order, TWO LINES of the same
product on one order (counted over DISTINCT orders, and over TEMPLATES, so two
lengths of one track count once - the common case since the merge), and a
DELIVERY CHARGE or down payment (services and anything unpublished are out,
which excludes the plastic filler by the rule that already makes it
unpublished).

### ONE POOL, NOT A HEADING PER FAMILY (owner, 2026-10-27)

*"i want the recommendations to be just one pool of products not multiple
categories, that way we dont show too many products in the recommendations."*

It was four headings with up to eight products under each, which on a kit page
is a second catalogue rather than a recommendation. Now it is ONE short row,
capped by the setting **"Add-ons to show"** (`aa_shop_addons.shown`, default 8
- two rows of four on a desktop), because "too many" is his judgement and not
a number for the code.

**THE FALLBACK POOL IS TAKEN IN TURNS ROUND THE FAMILIES**, and that is the
one place flattening four lists into one needs care: taken in sequence, a pool
of eight off his catalogue would be eight cones and nothing else, every cable
and track pushed off the end by whichever family happened to be listed first.

The families now do nothing but decide what is ELIGIBLE. A recommendation
fitting none of them is simply in the pool - his families were an answer about
cones, cables, tracks and trims, and his order book also knows about rollers
and hinges, which are the ones nobody would have gone looking for.

**THE CONES NOTE LOST ITS HEADING** and now sits under the section, shown only
when a cone is actually in the pool - asked by category OR BY NAME, because
his live catalogue has no Cones category at all and a warning that never
appears is worse than one that turns up beside a cone wrench.

**THE REVIEW SCREEN IS Website > Configuration > Recommended Add-ons**, every
pair with the number of his own orders behind it, grouped by product - one page
instead of twelve, which is the whole of what he asked for. "Orders before
recommending" is a SETTING (default 2, because one is an anecdote) with a
button beside it that counts again and opens the list, because a setting
nobody can try is a setting nobody touches.

Two things that cost a run each: **raw SQL must `flush_all()` first** (it reads
the database, not the ORM's pending writes - six tests failed on an order
confirmed a moment earlier), and **an unset `ir.config_parameter` reads as
`False`, where `int(False)` is a perfectly good 0** - which clamped to 1 and
made every coincidence a recommendation. The deploy's own log line said "at 1
orders or more".

The families are the LAST FALLBACK, found by website category name (`Cones`,
`Cables`, `Tracks`, `Trims`) with four settings under Website >
Configuration > Settings to point elsewhere. **The fallback is for an EMPTY
field, not an empty result**: a kit with one accessory set that happens to be
unpublished has still been got to, and falling back there would answer one
deliberate choice with every cable in the catalogue. A test holds that down,
because the first draft got it wrong.

**CONES ARE SHOWN ON THE SPRING PAGE WITH A WARNING.** The calculator prices
the cone set for the chosen I.D. into the spring itself, so a customer
configuring one is already buying cones. Asked whether to drop them: *"show
them but make it obvious that the cones are included so customers dont make
the mistake of buying when they dont need one."* So the spring carries the
note and a kit does not, where it would be a lie.

**THE WORDING IS HIS, WORD FOR WORD** (2026-10-28): *"Cones are already
included with your spring."* It is `CONES_INCLUDED` in
`models/product_template.py`; the tests compare against the constant rather
than quoting it, so changing the sentence again is one line and no test edit.

Templates are shown, not variants - a track is one product with twenty
combinations behind it since the merge, and twenty near-identical cards under
a kit is not a recommendation.

### HIS KITS ARE NOT `HK-` ANYTHING, AND THAT MADE IT ALL INVISIBLE

Owner, 2026-10-27: *"i dont see the recommended products under the kits, and
yes i did put the categories in the garage door add-ons in the settings."*

**His live catalogue has FOUR kits - `AA-1200`, `AA-1600`, `AA-1800` and
`AA-Custom` - in the WEBSITE category "Hardware Kits", and not one carries an
`HK-` part number.** This shipped looking for the twelve
`HK-<series>-<panels>P` products `garage_door_supply/hooks.py` creates, which
the shop does not sell. Nothing was read as a kit, every page drew nothing,
and no amount of setting the four family categories could have helped.

So a kit is now recognised by FOUR marks: the website category set in
Settings ("Hardware kits category", key
`aa_shop_addons.category_kits`), then the words *hardware kit* in the NAME, in
the product category or in any website category, then the `HK-` SKU last. **A
product that says "Hardware Kit" in its name is a hardware kit** - refusing to
read the name and demanding a part number was the mistake.

**THREE OF THE FOUR FAMILIES DO NOT EXIST ON HIS SITE.** The same crawl listed
his website categories: Drums, EBF, Hardware Kits, Hinges, Misc, Motors, Nuts
& Bolts, Rollers, Shafts, Springs, Tracks. Only *Tracks* matched - there is no
Cones, no Cables, no Trims. So the family lookup no longer insists on the
exact name: exact first, then the word (*Cables* finds *Lift Cables*), then
the singular (*Trims* finds *Trim Molding*), with the setting still the last
word. His cones and cables are presumably under Springs and Misc; tier 2 does
not care, because anything in no family goes under "Often bought with this".

**WEBSITE > CONFIGURATION > ADD-ONS CHECK answers "why do I not see them"** -
one line per product saying what its page will draw and where it came from.
It exists because answering that question once meant crawling the live site
with curl to find out what his products are actually called. **Read that
screen before theorising** about anything of this sort again - and remember
that his Prod catalogue is not what this repo's hooks create.

### SPRINGS SHOWED NOTHING, FOR TWO SEPARATE REASONS (owner, 2026-10-28)

*"recommended products only works with kits, springs doesnt currently show
anything in terms of recommendations, by the way this is specifically for
custom springs and the published items in the spring category."*

**ONE: THE CUSTOM SPRING IS NOT A SHOP PAGE.** It is configured on two
STANDALONE website pages - `/custom-torsion-spring` and `/spring-calculator`,
both calling `website.layout` directly - and the block was an inherit of
`website_sale.product`. No amount of recognising the product could have put a
block on a page that never renders the template carrying it. The block is now
a CALLABLE template, `aa_shop_addons.addons_block`, taking `aa_addons_product`,
and `views/spring_page_templates.xml` calls it into both pages. That is why
`aa_shop_addons` now depends on `spring_engineering`.

**AND THE CUSTOM SPRING PRODUCT IS NOT PUBLISHED**, deliberately, like the
plastic filler - so a VISITOR CANNOT READ IT and both pages answered **403**
the instant the block touched it. `_aa_custom_spring()` sudoes it once, and
the block sudoes what it calls. Only a test that FETCHES THE PAGE finds this;
the model-level tests all passed while the live pages were 403.

**TWO: A SPRING PAGE WAS ONE RECORD.** `_aa_addon_role()` returned "spring"
only for `product_custom_spring`, so the stock torsion spring pairs he
actually sells showed nothing. It is now the custom spring OR anything
published in the **Springs website category** (`aa_shop_addons.category_springs`,
default found by the name).

**BY CATEGORY AND NEVER BY NAME**, unlike kits: his catalogue carries a
"Spring Anchor Bracket" and a "3/8 x 1 1/2 Hex Tap Bolt (Spring Anchor Bolt)",
and a word match would have put spring add-ons on a bolt.

**HIS CONE SETS LIVE IN THE SPRINGS CATEGORY**, so they are spring pages too -
which is fine except for the cones note, and "already included with your
spring" under a cone set is untrue. `_aa_cones_note` therefore refuses to
fire on a product whose own name says cone.

**NOT IN `garage_door_supply`**, for the homepage reason below.

## The Custom Kit costs nothing, and must still be buyable (`aa_dealer_orders`)

Owner, 2026-10-27: *"there is a custom kit that should normally cost 0$ until
you start adding items, the problem is that the store doesnt detect that items
have been added to the kit so it still believes the price is zero, and when you
try to buy an item that costs 0$ it gives you a contact us button instead of an
add to cart button."*

**THE $0 IS DELIBERATE AND STAYS.** The parts carry the money, each on its own
line (owner, 2026-10-20), so the kit line is a HEADING - `custom_kit_data.xml`
says so - and a price on it would charge for the kit ON TOP of the parts.

What was wrong is ODOO'S ZERO-PRICE RULE. The website setting "Hide 'Add To
Cart' when price = 0" is a good rule and the shop keeps it; it just asks the
PRODUCT what it costs, and this product's honest answer is nothing.

**ODOO ENFORCES IT IN FIVE PLACES AND THEY SHARE NO HOOK**, all answered in
`custom_kit_zero_price.py`, keyed on the one `aa_custom_kit` boolean:
`_get_combination_info` (the Contact Us button), `_is_add_to_cart_allowed`
(the server's own refusal), `_website_show_quick_add` on BOTH the template and
the variant (the shop grid), `sale.order.line._check_validity` (raised while
adding) and **`sale.order._get_zero_priced_lines`, which blocks CHECKOUT**.
Finding four and missing the fifth would have been worse than finding none:
the customer gets further each time and still cannot pay.

Odoo's own exemption hook, `_get_product_types_allow_zero_price()`, is keyed on
`service_tracking` and only two of the five consult it, so it does not fit.

**`_get_combination_info` CANNOT BE CALLED UNDER `MockRequest`** - the mocked
pricelist comes back as a Mock and Odoo unpacks it two frames down
(`cannot unpack non-iterable Mock object`). Test it over HTTP instead, which
is the better test anyway. And **"Contact Us" appears in the site menu of
every page**, so a bare `assertNotIn` passes nothing: Odoo keeps both blocks
in the markup and hides one, so the assertion is `d-none` on
`#contact_us_wrapper`.

**The headline price follows the builder** (`showPrice` in `custom_kit.js`).
Display only - the cart is priced on the server from what the session
remembers - but a page saying $0.00 over a builder saying $236.91 is telling
the customer something untrue.

### AND AN EMPTY ONE CANNOT BE ADDED AT ALL (owner, 2026-10-28)

*"you shouldnt be able to add the custom kit to the cart when there is nothing
on it."*

**REFUSED IN THE CONTROLLER, BEFORE `super()`** - `add_to_cart` reads the
chosen parts (from the cart request, or the session where the page left them)
and raises if there are none, so Odoo never writes the line. Checking
afterwards would mean deleting a line the customer had just been told was
added. `_aa_custom_kit_picked()` is the single answer both the guard and the
packing read, because two readings of "empty" a moment apart is how a kit gets
in that the guard thought had parts.

**AND THE EXCUSE AT CHECKOUT IS NOW CONDITIONAL.** `_get_zero_priced_lines`
excuses a kit line only while `linked_line_ids` is non-empty - the whole
reason it may cost nothing is that the money is on the lines hanging off it,
so nothing hanging off it is a zero-priced line like any other. That also
catches what the controller cannot: a customer who DELETES every part out of
the cart and leaves the kit behind.

`_check_validity` stays permissive for the kit and must: it runs as the kit
line is written and the parts are hung off it a moment AFTER, so asking for
them there would refuse every kit, full ones included.

The button is disabled while the kit is empty, with the reason on it - a
courtesy, not the lock.

**A TEST ASSERTED THE OPPOSITE.** `test_an_empty_kit_adds_nothing_but_itself`
held that an empty kit still put its own line in the cart. That was never a
decision - only what the code happened to do, because the parts were added
after the line and an empty list added none. Rewritten, not deleted.

### THE X ON THE TAX-EXEMPT PAGE THREW A JAVASCRIPT ERROR (owner, 2026-10-28)

*"when trying to click the x on the top of the tax exempt dealer status page
i got this error ... Cannot read properties of null (reading
'defaultPrevented')"*

**`portal.portal_back_in_edit_mode` IS NOT A BANNER, IT IS THE CONTENTS OF
ONE** - a line of text plus a bare `btn-close` carrying
`data-bs-dismiss="alert"`. Called on its own, as `resale_templates.xml` did,
that button has no `.alert` above it: Bootstrap's `Alert.close()` looks for
the element it is meant to dismiss, finds null, and reads `defaultPrevented`
off it. **Every caller in Odoo's own code sets it as
`o_portal_fullwidth_alert`**, which the portal layout wraps in `alert
alert-info alert-dismissible` - that is the alert the X is for.

**AND IT WAS SHOWN TO EVERY PORTAL USER**, because ours carried no `groups`
while all of Odoo's do. A dealer reading their own certificate page was told
they were looking at a "preview of the customer portal" and offered a way
back into a back office they cannot open. It is `base.group_user` now.

The link went to GENERAL SETTINGS, which has nothing to do with the page; it
goes to the contact record, where the certificate is actually approved or
rejected. `/my/...` means the SIGNED-IN USER'S own partner - a member of
staff opening that page sees their own certificate page, not a dealer's.

A test asserts the shape the browser trips over: **any
`data-bs-dismiss="alert"` with no `.alert` ancestor**, read out of the
rendered page with lxml.

### SCAN THE QR TO DISPATCH (owner, 2026-10-28)

*"At pickup, the team scans the box sticker with a phone or tablet. Odoo opens
that order, checks every station is done and the invoice is paid, and marks it
Dispatched in one tap. the qr should be on one of the form that is printed out
at dispatch."*

**THE ACTION ALREADY EXISTED.** `action_aa_dispatched` has been the one button
since 2026-10-19. What is new is a way to reach it from a phone and two checks
worth making while somebody is holding the box.

Three things he decided when asked, each of which changed the build:

- **UNPAID BLOCKS, with no override** - the button is dead and says why.
  Checked again in the route, not only on the page that drew the button: a
  page can be open since this morning and a form can be posted to directly.
- **AN OPEN STATION ONLY WARNS** and can be gone past with a second tap,
  because a foreman can see the box is packed and the system is sometimes
  behind the shop.
- **A DEALER ON ACCOUNT PASSES THE PAYMENT CHECK**, saying ON ACCOUNT rather
  than UNPAID. A Quick Order raises no invoice at the time, so the rule would
  otherwise have blocked every dealer collection there is. Read through
  `_fields` because `aa_order_on_account` belongs to `aa_dealer_orders`.
- **THE QR GOES ON THE STICKER** - owner, 2026-10-28, correcting the form
  answer he gave an hour earlier: *"actually the qr code is supposed to be on
  the sticker."* The box sticker ALREADY had a QR and it already opened the
  "what is in this box" page, so **nothing new is printed on a 1 1/4 inch
  label**: that same page now also draws a Dispatch panel. ONE CODE, TWO
  AUDIENCES - a second QR would be two codes a phone has to choose between,
  and every sticker already on a shelf would be the wrong one.
  **THE PANEL IS NOT PUBLIC even though the page is**: it is drawn only for
  `stock.group_stock_user`, and `/box/<id>/<token>/dispatch` checks again
  rather than trusting that a button was ever shown. A fitter on a ladder
  scanning the same code still sees only the door's figures.
  A box belongs to a JOB and the button belongs to a TRANSFER, so
  `_aa_dispatch_picking()` joins them through the sale order and takes the
  OUTGOING one still to go out - a part-delivered order has a done transfer
  and a backorder, and the backorder is what somebody is standing there for.
- **THE QR IS ALSO ON BOTH PRINTED FORMS**, kept deliberately: a sticker only
  exists for a HARDWARE KIT job, so a spring-only order has no sticker at all
  and the Work Order Sheet is the only thing to scan. One line to remove from
  `report/dispatch_qr.xml` if he ever wants the forms bare.

**DOES IT DO WHAT HE ASKED? Checked clause by clause, 2026-10-28**, when he
asked exactly that - and two gaps came out of the asking, both the same
mistake as the 404:

- *"the team scans ... with a phone or tablet"* - A SHARED TABLET signs in
  once and keeps the panel; A PHONE OUT OF A POCKET never has, and drew the
  door's figures with NO SIGN THAT DISPATCH EXISTED. Nobody signs in for a
  button they have never seen. One discreet line now - "Staff: sign in to
  dispatch this order" - returning to that same sticker, shown to the PUBLIC
  only, because a dealer or fitter already signed in would not get the panel
  by signing in again.
- *"marks it Dispatched"* - A PACKED BOX WITH NO DELIVERY RAISED YET drew no
  Dispatch section at all, which looks identical to not being allowed one.
  **On `pick_ship` the outgoing delivery does not exist until the internal
  pick is validated**, so this is the likeliest thing to happen at the
  counter, not a corner. It now says so.
- *"Odoo opens that order"* - IT OPENS THE BOX, not the sale order form: the
  W/O number, the door, the kit and its figures, with Payment / Stations /
  Delivery under them. Deliberate - a phone at a counter wants the box, and
  the sale order form on a phone is unusable - but it is not literally what
  he wrote, and he has been told.
- *"checks every station is done"* - it checks every job on the order, and
  WARNS rather than blocks, which is his own earlier decision. Two taps then,
  not one.
- *"the invoice is paid"* - blocks, no override, re-checked in the route.

**IT IS NOT A PUBLIC LINK, unlike the box sticker.** `/box/...` only reads a
door's figures out loud; this one MARKS AN ORDER COLLECTED, and a public
version would let anybody who photographed a form empty the dispatch list. It
asks for a login and `stock.group_stock_user`. The token stays as well - a URL
that is only an id is a URL somebody edits.

**THE CHECKS READ WITH SUDO; THE DISPATCH DOES NOT.** A dispatch clerk has
stock rights and nothing else, so the first build answered **403** the instant
the page asked whether an invoice was paid. Being told "paid" is not the same
as being allowed to open the ledger. The dispatch itself is still done as the
person standing there, so `aa_dispatched_by` means something.

**HIS WAREHOUSE DELIVERS IN TWO STEPS (`pick_ship`)** - a fact worth keeping.
Confirming an order makes an INTERNAL pick and nothing else; the outgoing
delivery, which is the only kind `action_aa_dispatched` will touch, appears
once that pick is validated. Any fixture that wants a dispatchable transfer
has to validate the pick first.

**A STICKER THAT WILL NOT OPEN NOW SAYS WHY** - owner, 2026-10-28: *"when i
try scanning the qr code on the sticker it leads to a not found page."*

`/box/...` refuses for FOUR different reasons and said "Not Found" to all of
them, which at a counter is no help. It now carries the reason back and shows
it **to a signed-in member of staff only**.

**A PHONE AT THE COUNTER IS A STRANGER**, which is why that first fix changed
nothing for him: nobody is signed into Odoo on their own phone, so all four
reasons collapsed straight back into the bare 404 the reason page was written
to replace. A stranger now gets a page offering a **sign-in that returns to
the same link** - one tap to the reason instead of a dead end. It still names
none of the four: the page is IDENTICAL whichever it was, so it cannot be
used as an oracle for which box ids exist, and a test strips the one thing
that must differ (the echoed path) and asserts the rest is the same. All it
admits is that `/box/` is a route, which werkzeug's own 207 bytes already
admitted.

Two old tests asserted `404` on a public refusal and were REWRITTEN, not
patched around: the status code was never the decision - "the box does not
open" is.

**IT WAS THE HOST, AND IT WAS A MISSING `www`** - settled 2026-10-28 when he
sent the scanned link: `https://aaimpactgaragedoorsupply.com/box/131/571e5b68...`

That APEX DOMAIN IS NOT ODOO. It answers ten bytes of `text/plain` "Not
Found" to everything, `/web/login` included, and it does **not** redirect.
**His Odoo is at `www.aaimpactgaragedoorsupply.com`**, where that very link
returns the box page for W/O #234. So `web.base.url` on Prod is the apex and
every sticker ever printed points at a host that cannot serve it.

**NOTHING IN THE CODE WAS WRONG.** The job, the token, the route and the
sticker were all correct, and every test passed throughout - which is the
lesson: every test BUILT the link from `_aa_box_token()` and not one READ IT
OFF THE PRINTED STICKER. A test that constructs the URL it then fetches can
never notice that the label points somewhere else. `StickerHostCase` now
renders the report, digs the URL out of the QR's own `/report/barcode/`
query, and fetches it.

**HE PRINTED A SECOND STICKER AND IT WAS THE SAME** - owner, 2026-10-28:
*"im still getting not found on my phone, heres the link:
https://aaimpactgaragedoorsupply.com/box/132/bc5f7388a4bf525d6680b92e"*. Job
132, W/O #235, apex again: 404 there, 200 on `www`. Nothing had changed
because THE FAULT IS NOT IN THE CODE and the setting had not been touched -
and nothing of ours was on Prod either, main being unmerged. Worth
remembering that a code fix cannot answer a configuration fault, however many
times it is pushed.

**SO THE FIX IS A BUTTON NOW**: Manufacturing > Settings > Hardware Station >
"Sticker QR links" shows the host the stickers carry, warns when it is not
the address being read or is not frozen, and **"Use this site for sticker
links"** sets it from the ADDRESS BAR and freezes it in one click. Read,
never typed: the host somebody is looking at Odoo through is right by
definition, and a hostname anybody has to type is another week of this. It
refuses outside a browser rather than writing an empty host.

**AND IN THE END IT IS NO LONGER A SETTING AT ALL** - owner, 2026-10-28:
*"i dont see any technical option in the settings."* System Parameters sits
behind Settings > **Technical**, which does not appear unless developer mode
is on, so the fix I kept giving him was behind a door he could not open.

**A STICKER PRINTED FROM A BROWSER NOW CARRIES THAT BROWSER'S ADDRESS**
(`_aa_sticker_base_url`). Right by construction: somebody is looking at Odoo
through that host, so it serves Odoo, so the sticker opens. No setting to
find, nothing to type, nothing to get wrong - and it fixes itself on every
site, Prod, staging and dev alike.

**UNLESS THE BASE URL IS FROZEN, which is the line it does not cross.**
`web.base.url.freeze` is an administrator SAYING which host is right, and
being overruled by whoever last pressed Print would be worse than the fault.
Unfrozen, Odoo is already rewriting that parameter to whichever host an admin
last signed in from - so reading the request is the SAME POLICY applied per
label instead of per login, and strictly more accurate. A label printed in
the BACKGROUND has no request and still falls back to the parameter, which is
why it is still shown in Settings.

**WHAT THE APEX ACTUALLY DOES** - run down before any of this was written,
and not what "not a domain of his" first suggested: Odoo.sh redirects it to
`www` **for `/` only, dropping the path**. So `https://aaimpact...com/` 301s
to the www root and the domain looks perfectly healthy typed into a browser,
while `/web/login`, `/box/132/...` and every other deep path 404 - which is
all a sticker QR is. That is why nothing looked wrong with the domain.

**IT WAS NOT ONLY THE STICKERS.** Every page of the shop was declaring
`<link rel="canonical" href="https://aaimpactgaragedoorsupply.com/shop">`,
which 404s - Google being told the one true URL of each page is a dead one.
Same single cause. The canonical comes from the Website record's **Website
Domain** field (falling back to `web.base.url`), which is in Website >
Configuration > Settings and needs no developer mode.

**THE FIX BY HAND, if it is ever wanted**: set `web.base.url` to
`https://www.aaimpactgaragedoorsupply.com` AND `web.base.url.freeze` to
`True`, both in Settings > Technical > System Parameters.

**HOW TO TELL WHICH COMMIT PROD IS RUNNING, with no access to it**: probe a
behaviour only one version has. `/box/<id>/<bad token>` returning the
sign-in page with a `%2F`-quoted redirect is `343854e` and nothing earlier -
which is how it was established that he HAD merged, twenty minutes before
the commit he was looking for. Without the freeze
Odoo rewrites that host to whichever one an administrator last signed in
from, which is how it became the apex and how it will become something else
again - silently, because a QR code cannot be proof-read. The job form now
names the host beside the link and warns when it is not frozen. Stickers
already on boxes stay wrong until reprinted, unless the apex is made to
redirect to `www` at the DNS/registrar end, which fixes them all at once.

**HOW TO TELL ODOO FROM NOT-ODOO at a host you cannot log into**: fetch
`/web/login`. Odoo serves it; his apex 404s it.

**AND THE LINK IS NOW ON THE JOB** (Manufacturing > the kit job > Shop Floor
tab > "Box sticker link"). `aa_box_url` existed as a computed field and was
shown NOWHERE, so the only way to read what a sticker held was to point a
camera at it - which cannot tell a bad token from a bad host from a bad
camera. Clicking it opens exactly what the QR holds, from a browser already
signed in.

**WHAT THE ROUND TRIP IS NOT**: checked when the 404 persisted - the sticker
report, the token and the controller are `mrp.production` end to end
(`report/hardware_sticker.xml` has `model=mrp.production`, the token lives on
`MrpProduction`, and the route browses `mrp.production`). There is no
production/work-order id mix-up, and the 63 commits merged from Prod touch
nothing named `box_url`, `box_token`, `barcode_type` or `get_base_url`.

**HOW TO TELL A LIVE ROUTE FROM A MISSING ONE** without any access: fetch a
URL that route would refuse. The controller's own `request.not_found()` is a
BARE 207-byte werkzeug page; a path with no route at all gets Odoo's THEMED
website 404 of 32 KB. That is how the box route was proved to be live on his
Prod before anything was changed.

**`url_open(url, data={})` SENDS A GET.** An empty dict is falsy, so Odoo's
helper does not post - which reads as a 405 and looks like a routing fault for
half an hour. Post a real session csrf token instead; it belongs to the
session rather than to one form, so it can be taken off any page that has one.

## Pickup slots (`aa_pickup_slots`)

Owner, 2026-10-27: *"At checkout, the customer picks a pickup day and time
window, and it shows on the Work Order and in Dispatch ... Our lead time is 2
labor days, after those 2 days they choose when to pick up."*

Three answers he gave when asked, each of which changed what got built:

- **THE LEAD TIME STARTS THE NEXT WORKING DAY AND TAKES TWO WHOLE ONES.** An
  order placed **Monday** is collectable from **THURSDAY**; one placed Friday
  starts Monday and is collectable Wednesday. The day the order is placed
  never counts - an order placed at ten to five has had none of it.
- **ANY HALF HOUR FROM 7:00 AM TO 4:00 PM.** He first chose two-hour windows
  and revised it the same day - *"the customer should be able to choose
  anytime between 7 and 4, but dont make it a dropdown ... let them choose a
  larger range of time"* - so the time is stored as an HOUR OF THE DAY (7.0,
  7.5, 16.0) rather than one of four codes, and the open hours are a setting.
  The 19.0.2.0.0 pre-migration moves anything booked under the old windows to
  the START of the window it chose, which is what the customer was told.
- **PICKUP ORDERS ONLY, AND REQUIRED.** A delivery is never asked; a
  collection cannot be PAID FOR without a slot, so nothing reaches Dispatch
  blank for somebody to chase by telephone.

**A CHECKBOX SAYS WHICH DELIVERY METHODS ARE COLLECTIONS** - `aa_is_pickup`
on `delivery.carrier`, ticked once at install for anything that already reads
as one (`in_store`, or a name with *pickup* / *pick up* / *collect* in it) and
his after that. **No name matching at runtime**: a rule that cannot be turned
off is worse than a box somebody ticks, because the day "Pickup rate for
freight" is added it would start demanding slots with no way to refuse.

**THE CHECKOUT CONTROLS ARE A CALENDAR AND A GRID OF TIMES**, neither a
dropdown (owner, 2026-10-27). The calendar is drawn in the browser from the
days the SERVER says are allowed, sent down as `data-days`, so a square that
can be clicked is a day that will be accepted - one list, so they cannot
drift apart.

**`_check_cart_is_ready_to_be_paid` IS NOT THE GATE.** It is only reached on
the zero-total path in Odoo 19, so a pickup order with something to pay
walked straight past it - owner: *"currently they dont need to do either to
proceed."* The hook the payment page consults is
**`_get_shop_payment_errors`**, which is what `/shop/payment/validate` raises
on. Both are overridden. The checkout button is disabled too (both of them -
there is one for mobile and one for desktop), as a courtesy rather than the
lock.

**THE CART IS `request.cart` IN ODOO 19.** `website.sale_get_order()` is
gone, and the controller used it - so the route raised AttributeError the
instant a customer picked a date on the live site, with twenty-nine passing
tests behind it. THEY ALL TESTED MODELS AND NONE CALLED THE ROUTE. There are
now three that do, over HTTP, watching for a top-level JSON-RPC `error`,
which is exactly what a crash looks like and what a handled answer does not.
`request.cart` is already sudo'd, which is why Odoo's own delivery controller
names it `order_sudo`.

**THE TRANSFER STORES ITS OWN COPY of the day and time.** The Dispatch list is
a list of transfers and the first thing anybody wants is to SORT BY the pickup
time - who is coming this morning - and a related field through `sale_id`
cannot be ordered on in the database.

**IT IS KEPT IN STEP IN THREE PLACES, and writing it once was not enough**
(owner, 2026-10-27: *"i dont see the scheduled pickup date on the dispatch
screen, it showed up in manufacturing but not in dispatch"*). `_action_confirm`
puts it on; `sale.order.write` pushes a slot MOVED afterwards down, because
Dispatch reading Thursday while the order says Friday is worse than no column;
and `stock.picking.create` fills a BACKORDER from its order, because a
backorder is made by COPYING and these fields are `copy=False` - which is right
for a duplicated order and wrong for the half the customer comes back for.
Transfers already DONE or CANCELLED are never rewritten: what was on the
paperwork is a record. The 19.0.2.1.0 migration fills in the open ones.

### THE SLOT IS NOW THE SCHEDULED DATE (owner, 2026-10-29)

*"when the customer selects their order date it should be the scheduled date
in the work order, but currently the schedule date is the same as the time it
was ordered and the actual scheduled date is next to it"* - with a screenshot
of W/O #268 showing **Scheduled Date: Oct 29, 12:01 PM** and, in the field
beside it, **Mon 9 Nov, 1:30 PM**.

He is right that they were two things side by side. Odoo sets
`scheduled_date` when the order is CONFIRMED - the moment it was ordered -
and this module printed the real answer next to it in `aa_pickup_label`, so
the shop had to read the second and ignore the first. Now the slot IS the
scheduled date and the two agree.

**ONE PLACE, ON `stock.picking.write`.** The slot reaches a transfer by three
roads - confirmation, a slot moved afterwards, a backorder copying its order
- and keeping a stored copy in step across three of them is exactly what went
wrong with the Pickup column itself. All three end in a write of those two
fields, so the rule lives there and a fourth road cannot forget it. `create`
covers a transfer born with the slot already in its values.

**DONE AND CANCELLED ARE LEFT ALONE**, and it only moves when the SLOT moves -
somebody who sets a scheduled date by hand keeps it.

### THE MODULE HAD NO TIMEZONE, AND NOW IT NEEDS ONE

Every hour in `aa_pickup_slots` - the 7:00 to 4:00 he chose, the label, the
times offered at checkout - is SHOP LOCAL TIME, and nothing ever converted
because nothing ever left that world. `scheduled_date` is a naive **UTC**
datetime, so "1:30 PM" suddenly has to say which 1:30 PM it is.

**GUESSING WAS NOT GOOD ENOUGH, and the database was asked before deciding.**
Its candidates are a company calendar saying `UTC` (Odoo's default, not a
statement about the shop), a blank partner timezone, and the timezone of
whoever presses the button - which for a website customer could be anywhere.
So it is a SETTING, `aa_pickup_slots.timezone`, beside the opening hours it
belongs with, defaulting to **America/Toronto** - the fact already written
down here, that the shop works 7:00-4:00 Eastern. A mistyped zone falls back
rather than raising, the same call as the closed days.

**DST IS WHY THIS IS NOT ARITHMETIC**: 1:30 PM in July is 17:30 UTC and 1:30
PM in November is 18:30, and the shop says 1:30 PM both times. A test asserts
both.

**`stock.picking.state` IS A STORED COMPUTED FIELD.** The first version of
the "a finished transfer is left alone" test forced `state = 'done'` with raw
SQL; the next recompute put it back, so the test proved nothing while
appearing to fail. It validates the transfer for real now.

**The 19.0.2.2.0 migration** re-schedules every OPEN transfer that has a
slot, because W/O #268 and its fellows are already on his floor carrying the
date they were ordered.

**THE DISPATCH COLUMN IS NOT `optional`.** That was the whole of what he could
not see: an `optional="show"` column is shown only to somebody who has never
touched that list's column chooser, and anybody who has keeps the set they
saved - so a column added afterwards arrives HIDDEN behind the toggle at the
right-hand end. He has touched it; that list carries Dispatched and the
work-station badges. A column nobody can find is a column that is not there.
`Pickup Day`, the raw date, stays optional and exists for SORTING, because the
label reads "Fri 30 Oct" and sorts Friday before Monday.

Closed days (holidays) are a setting under Website > Configuration >
Settings; a mistyped date is ignored rather than raising, because a checkout
that 500s over a fat-fingered holiday is worse than a day staying open.

**A TEST THAT PASSED FOR THE WRONG REASON, and the lesson.** The one proving
payment is refused without a slot used a bare `assertRaises(ValidationError)`
and passed because ODOO'S OWN check - "the delivery method is not compatible
with your delivery address" - raised first, our code never running. It asserts
the message now, and the carrier in the fixture is `website_published` so
Odoo's checks pass and ours is actually reached. `super()` is called FIRST on
purpose: there is no point asking for a slot on a cart that is broken anyway.

## Station Time report (`aa_shop_floor`)

Owner, 2026-10-27: *"A dashboard from the timer history: average time per task
type, per worker, per day. Done when: you can see how long Michel takes per
spring order. (Only visible for admins)."*

**IT LIVES IN THE SHOP FLOOR, on the History dialog** - owner, 2026-10-27,
correcting where I first put it: *"it has to be in the shop floor module
itself, it would be best on the history option which is found when you click
the 3 bars on the top right."* A tablet bolted to a bench cannot reach a
Reporting menu in the back office. So it is a third tab, **Times**, beside By
day and Recent orders, with rows grouped Worker & task / Worker / Task / Day
and a 7 / 30 / 90 day period. **Worker & task is the default** because that is
the question - "Michel · Spring, 40 min, 12 jobs" answers it in one line.

A pivot also exists at Manufacturing > Reporting > Station Time for deeper
digging. He did not ask for it; it is one menuitem to delete if it is clutter.

**ADMINS ONLY, THREE TIMES OVER**: the tab is hidden unless
`aa_station_times_allowed()` says so, both server methods refuse a non-admin,
and the model's ACL is read-only to `base.group_system`. Hiding a button is
not a lock - what a man takes to do his work is not for the men beside him.

**IT READS THE TIMER LOG, NOT THE WORK ORDER**, and that is forced rather than
chosen. Shop Floor History lists `mrp.workorder` and shows `duration`, which
is the same clock - but a work order carries `employee_ids`, a MANY-TO-MANY,
and "how long does Michel take" cannot be grouped out of one. The log,
`mrp.workcenter.productivity`, carries `employee_id`, one per entry.

**ONE ROW PER WORKER PER JOB, summed from the entries.** A man who starts a
spring, breaks for lunch and finishes after leaves THREE entries; three rows
would make the average a third of the truth. So the average is over JOBS,
which is the question asked.

Deliberately excluded: **timers still running** (a duration still growing
averages in as however far into it somebody is) and **anything but productive
loss type** (Odoo logs a breakdown against the same work order, and counting
it would be a lie about Michel). A job with no `aa_station_kind` - a prepared
track from Odoo's own route - is kept as "Other" rather than dropped.

The day is the UTC date of the first entry. The shop works 7:00-4:00 Eastern,
which is 11:00-20:00 UTC, the same calendar day either way; a night shift
would need a timezone here.

Two things about Odoo 19 that cost a build each:

- **`mrp.workorder.product_id` IS NOT STORED**, so there is no column to
  select in the SQL view. The product comes off the production.
- **A search view's group-by `<group>` takes neither `expand` nor `string`**
  in 19. Both are rejected by the RELAX NG schema and the view will not load.

## The catalogue: ONE PRODUCT PER PART (owner, 2026-10-21)

*"ebp, hinges, rollers, shafts, angles, trims, and brackets should be one
product on the store, but in the individual product page people will be able to
then choose the other sizes or color"* - with the TYPE of part staying separate
(*"spring anchor bracket and top brackets will remain different products"*) and,
decided the same day, the hand on the product too: *"hands should be on the same
product, so another choice for rh or lh on the individual product"*.

89 products became 15, verified working by the owner on 2026-10-22. The table
that says which old product becomes which variant is
`spring_engineering/models/variant_families.py`; the engine is
`models/product_variant_merge.py`, which ran once from
`migrations/19.0.2.49.0/post-migration.py`.

**TO RUN IT AGAIN, USE THE SCREEN, NOT A DEPLOY.** Inventory > Configuration >
Catalogue Merge rehearses every family - performs them and rolls them back -
and shows the result with the reason under anything left alone; a "Merge for
real" button does it. THE MIGRATION WILL NOT RUN A SECOND TIME, because Odoo
only runs a migration for a version above the one the database holds and his is
long past 19.0.2.49.0. That screen is the only way in now, and it is why it
exists: the first real run merged one family of fifteen and the second thirteen,
and each round of fixes would otherwise have needed its own deploy.
`spring_engineering.variant_merge_hold` set to 1 makes a deploy rehearse only.

### What his own database taught this, and must not be undone

- **OPEN WORK FOLLOWS THE STOCK; IT DOES NOT BLOCK IT.** The first rehearsal
  refused THIRTEEN of fifteen families because W/O #204, #207, #208, #209 and
  AAM/MO/00072 held brackets and hinges. A working shop always has open work
  orders, so "validate or cancel them first" was a refusal that could never
  come right. An open move is unreserved, repointed and reserved again. Only a
  move somebody is part way through validating (`picked`) still refuses - that
  would throw away a count a person made at the rack.
- **A FAMILY NEED NOT BE SQUARE.** His hinges run #1-#9 and the Galvanized ones
  stop at #7, so nine sizes by three colours is 27 combinations over 25
  products. The two he has never stocked are ARCHIVED, which Odoo reads as
  "this combination does not exist" (`_is_combination_possible`). Refusing such
  a family - an earlier draft did - would have left four hinge sizes as
  separate products. To start selling a #8 Galvanized, un-archive that variant.
- **HINGE #8 AND #9 ARE ASSUMED TO BE THE SAME PART as #1-#7**, because the
  part numbers continue the same CH1411 series. They were not in the export the
  table was built from; the rehearsal named them as strays and they were added.
  Four lines to delete in `variant_families.py` if that is ever wrong.
- **A BARCODE IS MOVED, NOT COPIED.** It is unique per company and the old
  product is still active when the new variant is written, so copying one
  killed the Torsion Solid Shaft family with "Barcode CH-SH02-10FT6 already
  assigned".
- **VENDOR TAXES DIFFERING IS A NOTE; CUSTOMER TAXES DIFFERING IS A REFUSAL.**
  Both hinge families were refused because #8 and #9 carry a different purchase
  tax from #1-#7 - an accident of how they were entered, not a fact about
  hinges, and not worth leaving 43 products unmerged over. A customer tax, a
  unit or a product type differing still refuses: that would change what a
  customer is charged or re-measure the product.

Facts that came out of his export and should not be re-derived by guessing:

- **His internal references already group the families.** All four anchor
  brackets are `CH1119D`, all eight jamb brackets `CH1108`, all six EBPs
  `CH1128`. Part numbers are kept PER VARIANT, because hinges have one per size
  (`CH1411-1`..`-7`), and Cut Down Hinge is offset - #1 is CH1407 and #5 is
  CH1411, which collides with the Hinge family, so that one family cannot be
  grouped by SKU at all.
- **Colour never moves a price; size nearly always does.** The merge prices a
  variant as the product's price plus an extra per size, and refuses a family
  where two colours of one size disagree. Every variant's price is checked
  against its old product's before the family is committed.
- **Exactly one part is split by hand**: the spring anchor bracket. EBPs are
  sold "( Pair )", the Canimex drums are named by size.
- Tracks, drums, cables and cones are deliberately NOT folded in yet. Tracks are
  read by name all over the shop floor code and are their own job. 3" Lock IS
  folded in.

### Why this is NOT in garage_door_supply

That module owns `views/website_homepage.xml`, which replaces the whole of
`//div[@id='wrap']` and carries no `noupdate`, so EVERY update of it puts the
shipped hero back over whatever has been done in the website builder - the owner
restored a backup on 2026-10-19 and watched the page change back.
`aa_dealer_orders/__manifest__.py` refuses to depend on it for the same reason.
A merge needs a migration, a migration needs an update, and an update there
costs him his front page.

### The flag angle matches the TRACK'S SIZE (owner, 2026-10-22)

A **2" track takes the 5.9"**, a **3" track takes the 6-3/8"** - *"3\" do infact
use 6-3/8\", so could you make it so that 3\" tracks automatically use the
6-3/8\" and the 2\" tracks use 5.9\"."*

He first said every track takes the 5.9" and corrected it an hour later after
looking it up, so the earlier wording in this file was wrong for an hour. The
live site has been sending 5.9" to EVERY prepared track - not by rule, but
because the lookup ordered its matches by name and 5.9 sorts before 6-3/8. **So
3" prepared tracks already shipped carry the short angle and are wrong on the
job.**

`TRACK_PREP_FLAG_BY_TRACK_SIZE` in `spring_engineering/models/sale_order.py`
holds the pairing, and the track's size is read off its name or its part number
(`_track_prep_track_size_from_name` - the name leads with it, `CH-VT-3"` carries
it, and the length in the middle of the name is deliberately not read as a
size). Three tiers, in order: the angle stating this track's size wins; failing
that one that states NO size (the tolerance is for spellings - "Flag Angle -
Black"); and an angle stating the OTHER size is never substituted, because it
does not fit. A track that does not say what size it is gets no guess. The
setting `spring_engineering.track_prep_flag_product_id` is still the last word.

## The website door preview (`aa_door_preview`)

The 3D viewer on the product pages of aaimpactgaragedoor.com, which is
**WordPress on HostGator, not Odoo** - asked which site it should run on, the
owner chose the WordPress one (2026-10-26). So the deliverable is a plain
self-contained bundle, and `README.md` in that module has the embed snippet and
the file list for whoever has cPanel. **I write it; somebody else places it.**

It is in this repository anyway because the container is ephemeral, and
because Odoo serves the test page on a real origin at
`/aa_door_preview/static/src/preview.html`. The module has no models, no views
and no data - installing it changes nothing, and the manifest exists only so
the addons path serves the folder.

### ONE MODEL, THE COLOURS SWAPPED IN THE BROWSER

His Sirv account holds **one `.glb` per combination** of frame finish and
glass colour: all twenty, 8.84 MB each and 10.01 MB for the woodgrain ones,
about **180 MB**, and clicking a colour downloads a whole new door.

It does not need to. Every one of those files is the SAME single mesh - one
node, seven primitives, identical to within a few dozen bytes - differing only
in what its materials are set to, and the materials are named by role. So one
file is loaded, kept, and recoloured, which covers all twenty combinations.

**A CORRECTION, AND A LESSON.** I told him seven combinations answered 404 on
his live site and called it the strongest argument for the rewrite. IT WAS
WRONG. The file names are inconsistently cased - `White_Clear.glb` but
`White_green.glb`, `Wood_Grey.glb` but `Wood_white.glb` - and I had probed one
casing and read the 404s as missing files. All twenty exist; his viewer works.

A probe that assumes a naming convention is not evidence about what exists.
The real case for one model is 180 MB against 9 MB and instant switching, and
that needed no invented bug to stand up.

Facts read out of his own files on 2026-10-26, not to be re-derived by guessing:

- **glTF `baseColorFactor` is LINEAR.** Every colour goes in through
  `Color.fromArray`, never a hex string - a hex would come out roughly twice
  as bright. The full table of base colours, metalness, roughness and
  transmission is in that module's `README.md`.
- **`Frame_bronze` is dark in EVERY file**, the white and the woodgrain ones
  included (0.02 linear, near black), so it is a trim piece and not the frame.
  It is left alone; painting it would change a door he has already approved.
- **His Wood files put woodgrain on one frame piece and leave the other dark
  bronze.** The viewer makes the whole frame woodgrain, which is the
  consistent reading - **unconfirmed, and `FRAME_RE` is where to change it.**
- `Frane_Black` is a typo in his Black files. `FRAME_RE` matches `fra[mn]e`,
  so it is picked up either way.
- **`Blue_Circle` and `White_Circle` are the ROLLERS** - owner, 2026-10-27:
  *"the rollers are the circular objects on the side of the door ... all
  colors except white should have black rollers"*. So every finish but White
  sets them near-black (`BLACK_ROLLER`, 0.02 linear rather than 0, because a
  pure-black non-metal under a soft light is a silhouette with no shape in
  it); White restores what the file was built with, captured on load rather
  than typed in. Both materials were checked against the mesh first: they sit
  on the back face, at both side edges, up the height of the door.
- **THE "SMALL FLOATING SQUARES" ARE A PRIMITIVE, NOT A MATERIAL**, and
  reasoning from the material list alone got it wrong once. Owner,
  2026-10-27: *"there are some small floating squares on the front side of
  the door ... change the color of those squares to always be black, unless
  the door is white in which case they should be white, just like the
  rollers"* - and he OFFERED A PICTURE. I declined it and reasoned instead:
  of the six materials, three are already recoloured and `Frame_bronze` is
  the bottom seal, so `Silver` was the only one left and the only one whose
  colour never changed. Painting it turned every hinge, bracket and the track
  black - *"what you changed the color of was all the parts which is not what
  i wanted"* - and the square in the picture he then sent is WOODGRAIN. Frame
  material. **TAKE THE PICTURE WHEN IT IS OFFERED.**
  His mesh carries the frame material TWICE: one primitive of 8,083 vertices
  is the real frame, centred and 2.0 thick, and another of 3,791 is TEN
  BLOCKS AND NOTHING ELSE - five up the left edge, five up the right, one at
  each section joint - reaching out to 3.8 where the face is at 1.0. They
  stand a whole door-thickness proud of it, which is why they look detached.
  They are found BY SHAPE: the biggest frame mesh is the door, and any other
  frame mesh reaching well beyond it along the door's own thin axis is one of
  these (measured 0.106 past the face against a 0.038 threshold). No axis
  names and no primitive indices are written down, so a different model
  measures itself. **The material is CLONED first** - glTF shares one between
  the door and the squares, and three.js hands back the same object, so
  painting it in place paints the whole door. **The map is cleared too**, or
  a woodgrain door keeps woodgrain squares. **White is WRITTEN, not
  restored**, unlike the rollers: the point is to stop them taking the
  finish.
- **three.js r137.5 and its GLTFLoader are self-hosted** in `static/lib/` for
  the test pages, and come from a pinned jsDelivr URL in the pasted block -
  600 KB inline is a page editor's bad afternoon, and whether Sirv returns
  `application/javascript` for a `.js` file is not worth finding out on a live
  product page. The model itself comes from Sirv, which sends
  `access-control-allow-origin: *`.

### LITES ARE DRAWN, NOT MODELLED (owner, 2026-10-27)

*"make a test where i can see how it would look like choosing between 1-4
lites with 1 being the default"* - with four screenshots of his order form's
"Number of Lites". **Lites are panes ACROSS one section**, and the door is
always four sections tall.

**ONE IS WHAT HIS MODEL ALREADY IS.** Measured before any of it was written:
every opening in the `.glb` is clear - four sections, each a single unbroken
pane, no vertical divider anywhere. So 1 draws nothing and 2, 3 and 4 add
one, two and three bars per section. Had it been the other way about - a
centre stile to take OUT - it would have meant splitting his mesh apart,
which is a different job entirely.

**A BAR IS AS DEEP AS A RAIL, MEASURED ON ONE.** The first attempt sized it
from the frame's bounding box, which reaches around the whole door and takes
in the hinge lugs and the back seal: 0.182 deep and 0.053 off centre, where a
rail is 0.075 and dead centred. So the bars came out two and a half times too
deep and stood proud of the face - owner, 2026-10-27, *"the lites are jutting
out a bit on the front which looks a little ugly"* - and flush at the back,
because the error was all one way. A rail is the same member as a lite bar
turned the other way, so sampling one between the first two openings, away
from the ends, is exactly the right answer.

The bars are three.js boxes using the frame's own material, so they take the
finish and the woodgrain for free. **They are not his geometry**: dead on they
are indistinguishable, up close at an angle they are plainer than a real
stile. Fine for picturing a door, and if somebody is to ORDER from the
picture it wants a properly modelled `.glb` per layout - one file per layout,
not twenty, because the colours are swapped in the browser.

**THE AXES ARE WORKED OUT, NEVER NAMED.** His file is Blender's Z-up and the
node holding the mesh carries a quarter turn that swaps two axes on the way
in, so the door's height is the file's Z but the world's Y. Writing either
set of axis names into the code would be wrong half the time and silently so -
the bars would come out lying across the door like extra rails. So
`measureOpenings` identifies all three by what they look like: THROUGH the
door is the thinnest, UP is the one the sections stack along (more than one
pair of glass edges), ACROSS is the remaining one. Everything else - the
openings, the rail thickness that sets the bar width, the frame depth - is
measured off the model too, so a different door measures itself.

### SIRV IS BEING CANCELLED (owner, 2026-10-26)

*"we dont want to be using sirv, we want to unsubscribe from them to save
money so as long as this program you made works without them then we are
good."*

So **nothing may depend on Sirv.** The viewer needs exactly ONE of the
twenty models - the rest existed only because the old viewer wanted a file
per colour - so what moves is `White_Clear.glb` (8.8 MB) and `woodgrain.jpg`,
into a folder on HostGator, with the block's `data-model` and `data-wood`
pointed at them. `copy.html` has boxes for both and rewrites the block, so
nobody hand-edits 30 KB of pasted markup.

Paths must be **root-relative** (`/door-preview/White_Clear.glb`): a bare
relative path would resolve against `/products/series-1200/` and 404. The
content type does not matter - GLTFLoader reads an array buffer - so no MIME
configuration is needed, and same-origin means no CORS at all.

**THE BUILDER'S DEFAULTS ARE HIS SERVER, NOT SIRV, AND THAT MATTERS.**
`copy.html` pre-fills its boxes from the block's own defaults, so while those
defaults were Sirv URLs, re-copying the block to pick up a new feature sent
all three product pages silently back to Sirv - which is exactly what happened
on 2026-10-26, and would have taken the site down with the subscription. A
default must be the destination, never the thing being decommissioned. The
copy page now also states underneath the button where the block it just made
will load from.

A copy of `White_Clear.glb` is kept in `static/src/`. His server sends no CORS
headers, so the test pages cannot borrow the live files, and the alternative
was depending on the service being cancelled in order to test the thing that
removes the dependency on it. It is also a second copy of an asset he would
otherwise hold in one place.

**Download the files before the account is cancelled.** Afterwards they cannot
be fetched again, and the only copy of the texture in this repository is the
re-encoded JPEG.

three.js still comes from jsDelivr, which is free and not a subscription. It
can move to HostGator too via `data-three` / `data-gltf-loader`, with no code
change.

### The colour choices fold away (owner, 2026-10-26)

*"on mobile the choices block the visibility of the door so being able to hide
them to see the door fully would be better."* The arrow at the right of the
panel folds it to just itself in the corner. What is selected is still named
along the top of the frame, so hiding the chips loses nothing. It starts
OPEN - the choices are the point of the page, and a viewer that opens with
them hidden does not look like a configurator.

### ONE ELEMENTOR TEMPLATE SERVES ALL THREE SERIES PAGES

The viewer block lives in the Theme Builder template **"Product Single
Page"**, not in the three pages, so pasting it once reaches
`/products/series-1200/`, `-1600/` and `-1800/` together. The old Sirv
widgets were in that template too, which is why deleting them while editing
the 1200 took them off all three at once.

Expect that whenever a change seems to have applied to pages nobody touched -
it is the template, and it is correct. Anything genuinely per-series goes on
the page, or on the block as `data-frames` / `data-glasses`.

**Verified clean on 2026-10-26**, every page reachable from the homepage
crawled: no page requests Sirv. `scripts.sirv.com/sirvjs/v3/sirv.js` is
Sirv's public library and answers 200 without an account, so the leftover
widget would not have broken anything - it was 590 KB a visit for nothing.

### THE PRODUCT PAGES ARE ELEMENTOR, SO THE BLOCK CARRIES NO `<script src>`

An Elementor HTML widget does not have its markup parsed with the page: it is
set as `innerHTML`, and setting `innerHTML` **never executes an external
script**. The inline script is picked back out and re-run. So the first
attempt showed the viewer's own "could not load its renderer" message - its
code was running fine and three.js had simply never arrived (owner,
2026-10-26, with a screenshot of the Elementor editor).

`door_preview.js` therefore appends the library scripts itself, and leaves
`var THREE` null until they are in rather than reading it at parse time, when
there is nothing to read. **Putting script tags back in the snippet restores
the bug.** `static/src/elementor_test.html` reproduces that injection path on
purpose, so this never has to be diagnosed from a live page again.

The whole block is GENERATED by `tools/build_embed.py` from the stylesheet and
the script. Editing it by hand is how the website comes to differ from the
module, and then a fix made here stays broken there.

## Git

Never `git push`. Use `odoosh-push`.

### Commit and push without being asked (owner, 2026-10-21)

*"whenever you make a change you can commit and push automatically."* So finish
a piece of work by committing it and running `odoosh-push` - no asking first,
no leaving it uncommitted for the owner to remember. This container is
ephemeral: uncommitted work is lost on a rebuild, which is the whole reason for
the instruction.

TEST IT FIRST. "A change" means one that has been updated into the database and
had its tests run, not one that merely saves.

**WHEN THE HOST IS LOADED, RUN THE TESTS WITHOUT `-u`.** This container shares
a machine that has been seen at load 28, where `odoo-bin -u <module>
--test-enable` took FOURTEEN MINUTES to get through the module update and was
then killed by its own timeout, twice, before a single test ran. Once the
schema is current, `odoo-bin --test-tags /<module> --stop-after-init --no-http`
skips the update entirely and answers in under a minute. It found a NameError
in seconds that two abandoned runs never reached. A broken commit is worse than an
uncommitted one, because it reaches Prod the next time main is merged.

The push lands on this build's branch (`main`). Prod is still the owner's own
merge - never commit to or push the `Prod` branch directly.

## A minimum per part (`aa_min_max`)

Owner, 2026-10-29: *"make minimum and maximum of each item, same thing we did
for the spring in which we need to make a warning when an item is below its
minimum so that we can make a reorder of that product. I want you to show this
all in a new menu youll make in inventory, in the reporting tab, so that way we
can easily see the max and min of each item. the list doesn't currently show
the max so we can just worry about the minimum for now"* - with the filled-in
spreadsheet attached.

**HE FILLED IN 157 MINIMUMS AND LEFT 98 BLANK.** The blanks are his own rule,
written on the workbook's "How to fill" tab: *"Leave Min and Max blank for
parts you don't want to track."* They load as nothing at all and read as
**Untracked**, never as below - a blank taken for nought would put every nut
and bolt in the shop on the warning list. **Every maximum came back blank.**

**THE LEVELS LIVE IN ODOO'S OWN REORDERING RULES** (`stock.warehouse.orderpoint`),
not in two fields of ours. That is the design decision: a minimum stock level
is not a new idea, and putting his numbers there means the reorder he is
heading towards is **Odoo's Replenishment screen**, which counts incoming
purchase orders and applies the supplier's lead time. A field of our own would
have been a second truth to keep in step and would have had to be migrated
into reordering rules the day he wanted the purchase order.

**ODOO REFUSES A MAXIMUM BELOW THE MINIMUM** - "The minimum quantity must be
less than or equal to the maximum quantity" - so "minimum only" is not
directly storable. A blank maximum is written AS THE MINIMUM, which in Odoo's
terms means "order just enough to get back to the minimum". **The screen then
blanks a maximum equal to the minimum** (`NULLIF`), so the column stays empty
exactly where he left it empty instead of showing 157 rows of a figure he
never chose.

**THE RULES ARE WRITTEN `manual`, NEVER `auto`.** An `auto` rule is picked up
by Odoo's scheduler, which raises purchase orders by itself - and 97 of the
157 parts are ALREADY below their minimum, so installing this with `auto`
would have sent a wall of orders to four suppliers the same night.

### A PART NUMBER NO LONGER IDENTIFIES A PART

**THIRTY-TWO of the codes in his file are shared**, because of the catalogue
merge of 2026-10-21: `CH1108` is all EIGHT jamb brackets, `CH1119D` all four
spring anchor brackets, `CH1411-1` three colours of one hinge. Matching on the
code alone would have put one bracket's minimum on eight **and looked like it
worked**.

So the match is code first, then the variant's own name as Odoo prints it
(`Jamb Bracket (Black, #10)`) - the Product column of his file was generated
FROM his Odoo, so the names agree by construction. **THREE TIERS, STRICTEST
FIRST**: the full name, then ends-with, then contains. A loose match alone is
how `#1` swallows `#10` - `hingeblack1` is a substring of `hingeblack10`. His
hinges stop at #9 and his jamb brackets start at #10 so nothing collides
today; a test holds it for the day one does.

**NOTHING IS GUESSED.** A row matching no product, or still several after the
name, is REPORTED BY NAME and not loaded - "12 rows skipped" is not something
anybody can act on. A minimum silently on the wrong variant is worse than one
never loaded: the screen would call a part fine while the rack is empty.

**ODOO LEAVES A SINGLE-VALUE ATTRIBUTE OUT OF THE VARIANT NAME**, so a
one-colour fixture is named `Hinge (#1)` and tests nothing about
`(Black, #1)`. That cost a test run.

### ODOO DELETED THE MINIMUMS OF EVERY WELL-STOCKED PART (owner, 2026-10-29)

*"some items dont have a minimum set even though you had the information, for
example cut down hinges says no minimum set when on the excel it says the
minimum is 288 for some of them."*

**MY BUG, AND A NASTY ONE.** `stock.warehouse.orderpoint._unlink_processed_orderpoints`
is an `@api.autovacuum` whose entire test is:

```
create_uid == SUPERUSER_ID  AND  trigger == 'manual'  AND  qty_to_order <= 0
```

The loader wrote its rules with `sudo()` from the install hook - **superuser** -
and `manual` by deliberate choice, so Odoo's scheduler would not order
anything by itself. That is Odoo's own description of a throwaway rule, so the
moment a part was AT OR ABOVE its minimum and `qty_to_order` fell to nought,
Odoo binned it.

**THE HEALTHY PARTS LOST THEIR MINIMUMS AND THE SHORT ONES KEPT THEIRS**,
which is the worst possible half to lose: nobody looks at a part that is
fine, so it would have gone unnoticed until something ran out with no warning
at all. Cut Down Hinge is well stocked, which is exactly why it was one of
them.

**IT IS NOT ONLY THE NIGHTLY VACUUM**: `_get_orderpoint_action()` runs the
same cleanup, so merely OPENING Inventory > Operations > Replenishment does
it - which is the screen he was told to use.

**THE FIX IS ONE OF THE THREE CONDITIONS, and only one can be given up.**
`qty_to_order` is arithmetic; `trigger` must stay `manual` or 97 parts below
their minimum would send a wall of purchase orders out overnight. So the
rules are created BY A REAL USER (`levels_user()` - the current user if it is
not the superuser, then `base.user_admin`, then any active internal user).
Proved both ways on this build: superuser-owned rules vanish, admin-owned
ones survive.

**THE REPAIR IS A MIGRATION (19.0.1.1.0) IN TWO STEPS, AND THE ORDER
MATTERS.** First `repair_doomed_rules()` rebuilds the surviving rules under a
real user **keeping the numbers they hold**, because one may carry a minimum
he has changed by hand and the fault was who owned the rule, not what it
said. Then `load_levels(only_missing=True)` brings back the rules Odoo has
already deleted, **without writing over anything still standing**.

**THE REPAIR IS CONFINED TO THE PART NUMBERS IN HIS FILE.** Odoo makes
superuser-owned `manual` orderpoints of its own as scratch rows whenever
Replenishment is opened on a product whose forecast is negative, and deletes
them on purpose; repairing every rule of that shape would ADOPT them and fill
the screen with rules nobody asked for.

**A `str.replace(..., 1)` HIT THE WRONG FUNCTION.** The `with_user(owner)`
edit landed on the first `Orderpoint = ...` in the file, which was inside the
repair helper inserted moments earlier, and the module would not load
(`UnboundLocalError`). When a file has two identical lines, edit by line
number or by a unique anchor.

### "WHY HAS THIS ONE NO MINIMUM" IS NOW ON THE SCREEN (owner, 2026-10-29)

*"there are still some products missing, for example the flag angles."*

**THEY WERE NEVER IN THE FILE** - and the screen said "No Minimum Set", the
very same words it used for the ones Odoo had deleted an hour earlier. Two
completely different problems, one sentence, and no way for him to tell them
apart. Both times the only way to answer was for me to go and read the file.
That is the signal to build the screen, exactly as with Add-ons Check.

So every line of the file is now a record (`aa.minmax.level`, rewritten on
each load) with what became of it, and the report carries a **Why No
Minimum** column saying which of three things is true:

- *No figure was given for this part in the file* - nothing to fix but to
  type one;
- the row's own reason, in words, when it was given and could not be placed;
- *A minimum was loaded and has gone since* - which is what the superuser
  bug looked like.

**AND A PART NEED NOT HAVE A PART NUMBER.** The flag angles are why:
`spring_engineering` finds them with `name =ilike "Flag Angle %s"` and never
by a code, because they have not got one. The loader was keyed entirely on
part numbers, and worse, **the extraction that built the shipped file
REQUIRED a Code and dropped any row without one** - so a minimum he typed
against a flag angle never even reached the repository. A row with no number
is now matched by NAME: whole name, then ends-with, and never "contains" -
without a number narrowing the field to a handful of variants, a loose match
is being asked to pick one product out of the whole catalogue, and
"Flag Angle Black" would happily find "Flag Angle Black 6-3/8". Several
matches is a refusal, as always.

**WHERE A NUMBER NAMES EXACTLY ONE PRODUCT THE NAME IS IGNORED**, which is
deliberate and worth keeping: his file's names came out of a STAGING database
and a part may have been renamed since. The number is already unambiguous. A
test asserts it - the first draft of that test assumed the opposite and
failed.

### HE SENT THE FILE AND HIS PRODUCT LIST, AND IT WAS 36 MINIMUMS SHORT

**HIS FILE HOLDS 193 MINIMUMS. ONLY 157 WERE SHIPPED.** The 36 missing are
EXACTLY the rows with no part number, because the step that turned his
workbook into `minmax_levels.csv` required a Code and dropped anything
without one. All four flag angles, eighteen RAW track lengths, Cut Down Hinge
#6-#9, Hinge #8-#9, the hollow shaft and a drum. He found it by looking;
nothing in the code could have, because the rows never reached the
repository.

**84 OF HIS 112 PRODUCTS HAVE NO PART NUMBER**, and **161 of the 193
minimums can only be placed by name**. Name matching is the MAIN PATH here,
not a corner - which is the opposite of what the first build assumed.

**THREE ATTEMPTS AT MATCHING BY NAME, and his catalogue killed the first
two:**

1. `name ilike "<the whole row>"` - can never match a VARIANT, whose `name`
   is its template's (`Flag Angle`) while the row says
   `Flag Angle (Black, 5.9")`.
2. Cut the row at its first bracket to recover the template name - and
   `Bottom Bracket ( Pair )` and `End Bearing Plate ( Pair )` are template
   names WITH A BRACKET IN THEM, so the cut lands mid-name. Eight rows.
3. **Parse nothing.** Index every product's own `display_name` - exactly what
   Odoo prints - once, and look the row up in it. `name` is indexed too, for
   single-variant parts. Exact only, never "contains": without a part number
   narrowing the field to a handful of variants, a loose match is picking one
   product out of the whole catalogue.

**REHEARSED AGAINST HIS REAL CATALOGUE before shipping**, by rebuilding his
112 templates (and their variants, inferred from the bracketed suffixes in
his own rows) into 476 products and running the real loader: **193 of 193
placed, none unmatched.** That is the check worth repeating whenever this
file changes - an export of his products plus the workbook is enough to know
the answer before he merges.

A single-value attribute is left out of a variant's name by Odoo, so the
rehearsal skips any dimension with one value; a family that is genuinely
one-colour would need care.

### A NEW MODULE IS NOT INSTALLED BY MERGING (owner, 2026-10-29)

*"im not seeing it in reporting"* - with a screenshot of his Prod showing
Stock, Locations, Moves History and Moves Analysis, and no Min / Max Levels.

**MERGING A BRANCH ONLY UPDATES MODULES THAT ARE ALREADY INSTALLED.** A module
that did not exist before sits in Apps waiting for somebody to install it, and
nothing about a deploy says so. Every new module in this repository has needed
that step; this is the first time it was noticed, because every earlier one was
installed on a dev build first.

**`auto_install: True` DOES NOT FIX IT ON A LIVE DATABASE.** Proved here by
uninstalling the module and running both `-u aa_spring_stock` and `-u base`:
neither brought it back. The auto-install decision is the SQL in
`odoo/modules/db.py::initialize()`, and `load_modules` calls `initialize()`
only when the database **is not yet initialised** - so it fires on a fresh
build and never retro-installs. It is kept for new builds; it is not the
answer.

**SO THE MODULE IS AN APPLICATION**, which is: Odoo's Apps screen filters to
applications by default, so `application: False` makes a module invisible
there unless somebody knows to clear a filter. The one person who would have
to is the one who asked for the screen.

**A MANIFEST KEY WRITTEN TWICE IS SILENT.** The scaffold already carried
`'application': False` and the fix added `'application': True` above it; a
Python dict literal takes the LAST one, so the module installed and reported
`application=False` with both lines plainly visible in the file. Read what
Odoo loaded (`get_manifest`), not what the file appears to say.

To install on Prod: **Apps > Update Apps List**, search *Min / Max*, Install.
Once only - after that it updates with every other module.

### The screen

**Inventory > Reporting > Min / Max Levels**, where he asked for it. It opens
on **Below Minimum**, because "what needs ordering" is the question it exists
to answer; every part is one click away on the Status filters.

**"SHORT BY" IS THE COLUMN THAT MAKES IT USABLE.** Ninety-seven parts are
below their minimum on day one, since the minimums cover 180 doors. A screen
of 97 red rows in no particular order is 97 rows of undifferentiated alarm;
sorted by how far below, the top of it is what to ring the supplier about this
morning.

A report is a DATABASE VIEW and cannot be typed into, so each row has a button
opening its own reordering rule - the minimum he disagrees with is the one he
wants to change there and then. Loading is re-runnable from
`action_load_levels`; the first install does it from `post_init_hook` and sets
`aa_min_max.levels_loaded` so a later update never undoes his edits.

**HIS VENDOR COLUMN IS LOADED TOO** (Iowa Spring, CHI Hardware, Arrow
Tru-Line, Action Industries) onto any part that names NO vendor - Odoo cannot
raise a purchase order without one, and leaving it on the floor means asking
him for the same thing again. **It never overwrites**: a part that already
names a vendor is purchasing's own data, with prices and lead times behind it.

## Spring coil stock (`aa_spring_stock`)

Coils are COIL-<wire>-<I.D.>-<L/R>, in inches, one lot per piece, under
AAM/Stock/Rack (leftover pieces), /Floor (coils in use) and /Boxes (unopened).
A Springs MO reserves, when confirmed, the piece each spring is cut from and
consumes it when done. Order of preference (owner, 2026-10-19): a Rack piece
that is long enough, then the Floor, then the Boxes - the shortest piece that
fits in each. A coil taken from a Box is moved to the Floor once cut. A piece
left shorter than 16" is scrapped; 16" or more stays where it is. A spring
with no matching coil never blocks the order: it is logged as a problem cut.

### HOW LONG THE COIL WILL LAST (owner, 2026-10-28)

*"Spring Engineering already knows the inches every order cuts. I want it to
track the spring wire size and id inventory and send a warning somewhere that
at the current pace of orders being made we will likely run out of material in
x amount of days."*

**NOTHING NEW IS MEASURED.** Both halves were already recorded:
`aa.spring.cut` has logged every spring ever cut - dated, with its wire, its
I.D. and its inches - and the quants hold what is left. The feature is one
division, and all the work was in deciding what the two numbers mean. It is
three columns on `aa.spring.stock.summary` (Inventory > Springs > Spring
Inventory): **Days Left**, **Used / Day** and **Cuts** counted.

Asked where to put the warning he chose **the stock screens and NO EMAIL**
("lets not do emails for now"), and **14 days** as the line.

- **ON SPRING INVENTORY, NOT ON FLOOR / RACK / BOXES.** Days-left is a figure
  per wire and I.D. across every place; on a *Floor* row it would silently
  include Box stock and be a number that does not belong to the row it is on.
- **THE WORSE HAND DECIDES.** A spring takes a LH piece AND a RH piece, so a
  size with a mountain of LH and no RH has run out - the same reasoning as the
  pairs alert. `days_left` is the smaller of the two hands, and **Postgres
  `LEAST` returns the smallest NON-NULL**, which is what makes a hand nobody
  orders drop out of the comparison instead of dragging it to zero.
- **FREE INCHES, NOT INCHES**: `quantity - reserved_quantity`. A confirmed
  order has already reserved the piece each spring is cut from, and counting
  those inches would promise material that is spoken for. The reservation IS
  the planned cut, so this needs no join to the cut log.
- **NO PACE MEANS NO ANSWER.** A size nobody has cut in the window shows
  BLANK - not a warning, not "forever". He asked what happens at the CURRENT
  pace; a warning on a size that never moves is the noise that costs the real
  ones their credibility.
- **A CUT NOBODY COULD MAKE IS STILL DEMAND.** The pace counts `done` AND
  `short` - `short` being an order that wanted that size and found no piece
  long enough. Leaving those out understates the pace exactly when stock is
  tightest. They cannot double-count: a replan unlinks a cut that is not done
  before writing the new one. `planned` is excluded, because its inches are
  already off the free figure through the reservation.
- **JOINED BY PRODUCT, NEVER BY THE LABELS.** `aa.spring.cut` stores
  `inside_diameter` as the pretty label (`2 5/8"`) and `wire` as the code
  (`262`), while the summary groups by `2.625`. Matching those Char columns
  would line up nothing at all; the coil's `default_code` is the one spelling
  both sides already agree on.
- **UTC EXPLICITLY** in the window: `aa_spring_cut.date` is a naive timestamp
  holding UTC, and bare `now()` is a timestamptz that Postgres would cast
  using the SESSION's timezone, sliding the window by however many hours that
  is.

Both numbers are SETTINGS under **Inventory > Configuration > Settings** -
"Warn under (days left)" (`aa_spring_stock.runout_warn_days`, 14) and
"Measure the pace over (days)" (`aa_spring_stock.pace_days`, 30) - read LIVE
by the SQL view, so changing one changes the screen with no module update. A
mistyped value falls back to the default rather than taking the inventory
screen down, the same call as the pickup holidays. The xpath anchor is
`warehouse_setting_container`; **there is no `traceability_setting_container`
block** in Odoo 19's stock settings, which is one install failure.

`runout` lives in the DATABASE rather than in a Python compute, which is the
only reason "Running Out" can be a search filter and the column can be
sorted on.

**IT FOUND A BUG: EVERY SPRING ORDER WAS RESERVING ITS COIL TWICE.** Raising
`move.product_uom_qty` on a confirmed move makes Odoo assign it immediately,
off whichever quant it likes, and `_aa_plan_coil_cuts` then added its own
deliberate line ON TOP - 120" reserved against a 60" demand. **It never lost
material**: the right inches come off at `done`, which the consumption tests
prove. What it did was HIDE GOOD COIL - `_aa_coil_pieces` offers
`quantity - reserved_quantity`, so a piece with plenty left looked too short,
pushing the next order onto the Floor, then the Boxes, and eventually logging
"No piece is long enough" with a full coil on the rack. Odoo's guess at the
lot is now REPLACED rather than added to, since this code has already chosen
the piece by his order of preference.

**A PRE-EXISTING FAILURE, NOT THIS:** `test_adjust_changes_removes_and_adds_pieces`
fails on a clean tree (checked by stashing) - `(2, 0) != (1, 1)`. Adding a
piece of the OTHER HAND from the Adjust dialog appears to create it on the
hand of the row the dialog was opened from, so an RH coil added there becomes
an LH one. `action_apply` does read `line.hand` (spring_adjust.py:189), so it
is not simply that; it was not run down because it is nothing to do with the
run-out figure. Worth fixing - it corrupts the very stock this reports on.

## THE DEALER'S NOTE REACHES THE JOB (`aa_shop_floor`, owner 2026-10-30)

*"when notes are made on the dealer quick order, i cant see the notes on the
manufacturing page for that order, could you fix that."*

**IT WAS NOWHERE DOWNSTREAM.** The Quick Order has always stored it, into
Odoo's own `sale.order.note` (`aa_dealer_orders/controllers.py`, trimmed to
2000 characters) - but **`mrp.production` has no note field of its own** and
nothing here ever reached back for it. The note sat on the order where only
the office looks. It is still not on the printed Work Order Sheet or the
bench card; he was told.

`aa_order_note` on `mrp.production`, **NOT STORED** - it is a paragraph a man
reads before he builds, with nothing to search or sort on, and an office that
corrects a note wants the correction on the bench's screen at once.

**THE JOB FINDS ITS ORDER TWO WAYS**, as everything here must:
`aa_sale_line_id`, then the Source Document by name - a prepared track job
from Odoo's own route carries nothing else.

**ABOVE THE NOTEBOOK, NOT IN THE SHOP FLOOR TAB.** That page is hidden unless
the job has a shop spec, and "cut the tracks two inches short" matters on
every job there is. A note behind a tab nobody opens is the fault being
fixed. `role="status"`, not `alert`: Odoo's view checker reserves the alert
roles for things that stop what you are doing.

**ITS LINE BREAKS WOULD HAVE BEEN LOST, SILENTLY - and the first fix for
that did not work.** `sale.order.note` is an HTML field, but what the Quick
Order writes into it is the raw contents of a textarea, and in HTML a newline
is whitespace: "cut 2 inches short\nblack track" renders as ONE RUN-ON LINE,
which is how a two-line instruction becomes one wrong one.

The obvious answer - run it through `plaintext2html` when it has no markup -
**fails, and a test found that rather than reasoning**: Odoo's Html field has
ALREADY wrapped the textarea's contents in `<p>...</p>` by the time anything
reads it, newlines and all. So "does this look like HTML" answers yes for
both kinds and tells you nothing.

So nothing is sniffed and nothing is rewritten: the note is wrapped in
`white-space: pre-wrap`, under which a literal newline is a line break and
real markup is still markup. Both kinds come out right.

### AND IT WAS ON THE WRONG SCREEN (owner, 2026-10-30)

*"i dont see the note, could you put it on this tab and on the work order
sheet as well"* - with a screenshot of **W/O #299**, open on its **Note** tab.

**HE SAID "THE MANUFACTURING PAGE" AND I DECIDED WHICH MODEL THAT WAS.** The
first build answered `mrp.production`, which is a defensible reading of the
words and the wrong one: the screenshot shows Check Availability, Validate,
Source and Destination Location, PO Number and Source Document - that is a
**`stock.picking`**, shown under Manufacturing > Work Orders, which is the
screen the shop actually works off. The note went on a record he never
opens, and every test passed. **The same mistake as the sticker's host: the
picture settles what the words cannot.**

So `aa_order_note` is on `stock.picking` too, and the rule is in ONE place -
`readable_note()` in `work_order_sheet/models/order_note.py`, which
`aa_shop_floor` imports (it already depends on this module). Two copies of
"how a dealer's note is made readable" is how one of them comes to lose its
line breaks again.

**ON THE NOTE TAB HE POINTED AT, ABOVE ODOO'S OWN `note`, AND NOT INTO IT.**
The transfer's own note stays the shop's to write in - *"Packed by Michel"* -
and copying the order's words into it would leave two of them, the one on the
transfer going stale the moment the office corrects the order. NOT STORED, for
the same reason as the job's.

**AND ON THE PRINTED SHEET**, which is the half he had to ask for twice: the
cover in the shop's own red under the PO, and a compact NOTE box on EVERY
station page, for the same reason the door's size and the PO are repeated -
the sheet is split up and handed out, and "cut the tracks two inches short"
is for whoever is cutting the tracks. `t-set` at ARTICLE scope beside `po`,
`sections` and `door`, never inside the cover: the station pages are its
siblings.

An order with no note prints no heading rather than an empty box.

### Spring boxes (owner, 2026-10-19)

Springs come in big supplier boxes and stay boxed until the floor has room; box
coils are used last. Each numbered box (`aa.spring.box`) is its own location
under Boxes (`AAM/Stock/Boxes/Box 3`) and can hold several wires / I.D.s. Coils
are added per line (I.D., wire, LH and RH count; one 84" lot each, named
`BOX<n>-<wire>-<I.D.>-<hand>-NN`), moved down to the floor a chosen number at a
time, and a box is removed only once it is empty. Floor, Rack and Boxes are
shown on ONE page, a fold-out group per place (owner, 2026-10-19: not separate
menus) - `aa.spring.place.summary`, menu "Floor / Rack / Boxes". Anything that asks "is this a
box coil" must use `place_of()`, never `location.name == "Boxes"`.
