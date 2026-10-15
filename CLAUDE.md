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

Treated as a supplier cost, so the markup applies to it, the same as the cones
(owner, 2026-10-15).

### The steel rate is an ordinary setting

Editable in Website > Configuration > Settings like the markup and the labour
charge, but not secret - it is a commodity price. Default $1.46/lb, in
`spring_engineering/pricing.py`.

### How the pieces fit together (owner, 2026-10-15)

- The per-pound setting ("Spring sell price per pound", key
  `spring_engineering.steel_per_lb`) is a SELL price with the labour already in
  it. It is NOT marked up.
- Cones and the plastic filler are charged on top at cost x the markup
  (`spring_engineering.markup_percent`, "Cones & filler markup" in Settings).
- There is no separate labour charge any more; the "Assembly labour" setting
  was removed and `_labor_flat()` returns 0.
- Cone and filler COSTS live in `spring_engineering/pricing.py`, server side.
  The browser is never told the markup; it receives rates with it applied.

### Hardware station

Each hardware kit line gets a "Pack hardware kit" MO (kit, color, panels, rollers,
drum, track, lift, door size, weight) and each prepared lift cable pair gets a
"Cut lift cables" MO (size, cut length = the pair's reel feet / 2, sleeve, thimble,
stop per cable). The station BoMs are NORMAL, template-level, with no components:
the delivery still explodes the kits' and cables' own phantom BoMs.

## Git

Never `git push`. Use `odoosh-push`.
