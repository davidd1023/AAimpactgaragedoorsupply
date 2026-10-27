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

**NOT IN `garage_door_supply`**, for the homepage reason below.

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

## Spring coil stock (`aa_spring_stock`)

Coils are COIL-<wire>-<I.D.>-<L/R>, in inches, one lot per piece, under
AAM/Stock/Rack (leftover pieces), /Floor (coils in use) and /Boxes (unopened).
A Springs MO reserves, when confirmed, the piece each spring is cut from and
consumes it when done. Order of preference (owner, 2026-10-19): a Rack piece
that is long enough, then the Floor, then the Boxes - the shortest piece that
fits in each. A coil taken from a Box is moved to the Floor once cut. A piece
left shorter than 16" is scrapped; 16" or more stays where it is. A spring
with no matching coil never blocks the order: it is logged as a problem cut.

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
