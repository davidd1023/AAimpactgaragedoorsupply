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
- `Blue_Circle` and `White_Circle` are unidentified and left untouched.
- **three.js r137.5 and its GLTFLoader are self-hosted** in `static/lib/` for
  the test pages, and come from a pinned jsDelivr URL in the pasted block -
  600 KB inline is a page editor's bad afternoon, and whether Sirv returns
  `application/javascript` for a `.js` file is not worth finding out on a live
  product page. The model itself comes from Sirv, which sends
  `access-control-allow-origin: *`.

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
had its tests run, not one that merely saves. A broken commit is worse than an
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
