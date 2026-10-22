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

## The catalogue: ONE PRODUCT PER PART (owner, 2026-10-21)

*"ebp, hinges, rollers, shafts, angles, trims, and brackets should be one
product on the store, but in the individual product page people will be able to
then choose the other sizes or color"* - with the TYPE of part staying separate
(*"spring anchor bracket and top brackets will remain different products"*) and,
decided the same day, the hand on the product too: *"hands should be on the same
product, so another choice for rh or lh on the individual product"*.

81 products became 15. The table that says which old product becomes which
variant is `spring_engineering/models/variant_families.py`, GENERATED from his
own catalogue export; the engine is `models/product_variant_merge.py` and it
runs once, from `migrations/19.0.2.49.0/post-migration.py`. It rehearses first
and logs both passes; a family that does not add up is left alone and named.
`spring_engineering.variant_merge_hold` set to 1 makes it rehearse only.

Facts that came out of his export and should not be re-derived by guessing:

- **His internal references already group the families.** All four anchor
  brackets are `CH1119D`, all eight jamb brackets `CH1108`, all six EBPs
  `CH1128`. Part numbers are kept PER VARIANT, because hinges have one per size
  (`CH1411-1`..`-7`), and Cut Down Hinge is offset - #1 is CH1407 and #5 is
  CH1411, which collides with the Hinge family, so that one family cannot be
  grouped by SKU at all.
- **Colour never moves a price; size nearly always does.** The merge prices a
  variant as the product's price plus an extra per size, and refuses a family
  where two colours of one size disagree.
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

### A prepared track takes the 5.9" flag angle (owner, 2026-10-22)

*"every track takes 5.9" currently, that other size is for other things."*

It was getting that answer by ALPHABET - the lookup ordered its matches by name
and 5.9 sorts before 6-3/8 - which held only while the catalogue had exactly two
sizes spelled exactly that way. It is now asked for by size
(`TRACK_PREP_FLAG_SIZE_RE` in `spring_engineering/models/sale_order.py`), and if
there is no 5.9" the preparation refuses itself rather than substituting the
other size, because the other size is for other things. The setting
`spring_engineering.track_prep_flag_product_id` still answers for a catalogue
that has no 5.9" at all.

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
