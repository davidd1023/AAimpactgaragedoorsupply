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

### Hardware station

Each hardware kit line gets a "Pack hardware kit" MO (kit, color, panels, rollers,
drum, track, lift, door size, weight) and each prepared lift cable pair gets a
"Cut lift cables" MO (size, cut length = the pair's reel feet / 2, sleeve, thimble,
stop per cable). The station BoMs are NORMAL, template-level, with no components:
the delivery still explodes the kits' and cables' own phantom BoMs.

## Git

Never `git push`. Use `odoosh-push`.

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
