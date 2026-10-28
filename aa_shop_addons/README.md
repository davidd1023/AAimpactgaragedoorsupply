# Shop add-ons

The parts a customer still needs, shown under the kit or the spring they are
looking at. Owner, 2026-10-27: *"On every kit and spring page, show the
matching add-ons (cones, cables, tracks, trims) below the product. Done when:
each kit shows its correct add-ons."*

## Who decides what is "correct"

**Three answers, in this order.** What he picked, then what his own orders say,
then the families.

| tier | where it comes from | when it is used |
|---|---|---|
| 1 | **Alternative Products** on the product | whenever the field has anything in it |
| 2 | **his own order book** - products bought on the same orders | when the field is empty and the counting found something |
| 3 | the four **families** by website category | when neither of the above has an answer |

Whichever tier answers, the result is **ONE POOL** - owner, 2026-10-27: *"i
want the recommendations to be just one pool of products not multiple
categories, that way we dont show too many products in the recommendations."*
It was four headings with up to eight products under each, which on a kit page
was a second catalogue rather than a recommendation. Now it is one short row,
capped by **Website → Configuration → Settings → Add-ons to show** (eight by
default: two rows of four on a desktop).

The families no longer put headings on the page - they only decide what is
eligible, and the pool is **taken in turns round them**. That matters: taken in
sequence, a pool of eight off his catalogue would be eight cones and nothing
else, every cable and track pushed off the end by whichever family happened to
be listed first.

A hardware kit knows its series and its panel count and nothing else. What
picks one cable out of twelve is the door height and the drum; what picks one
track is the height, the track size and the colour. None of those live on the
kit, so any **rule** the code invented would be confidently wrong - which is
why tier 2 is not a rule.

## Tier 2: counted, not guessed

Owner, 2026-10-27: *"could you automate a system that will recommend additional
products the same way that the alternative product thing works. this way i wont
have to individually go into every products page to seach which products i
should recommend alongside it."*

**He had already answered the question, at the counter, all year.** "Which
cable should go with this kit" is an engineering question nothing here can
answer. "Which cable do people who buy this kit buy" is a **counting** question,
and the answer is sitting in `sale_order_line`.

So every night the pairs are counted: for each kit and the custom spring, the
other products that appear on the **same order**, and a product is recommended
once enough real orders have carried both. Nothing is invented - everything it
says, his own shop has done. It cannot recommend something nobody has ever
bought alongside, which is also the reason it can be trusted with a page
nobody has reviewed.

### Seeing what it decided, in one place rather than twelve

> Website → Configuration → **Recommended Add-ons**

Every pair, which product it shows under, and **how many of his own orders are
behind it**. Grouped by product. Nothing has to be done on this screen; it is
for looking at - and the one line somebody disagrees with is fixed by setting
Alternative Products on that product, which wins outright.

`Count the orders again` rebuilds it there and then; it also runs nightly on
its own.

### The one number

> Website → Configuration → Settings → **Garage Door Add-ons** →
> *Orders before recommending*

**Two by default, because one is an anecdote.** It is a setting rather than a
constant because what counts as a habit depends on how much history there is:
set it to 1 on a young catalogue to see what comes out, raise it once there is
enough to be choosy. There is a button beside it that counts again and opens
the list, because a setting nobody can try is a setting nobody touches.

### Four things the count refuses to be fooled by

- **A quotation nobody accepted** is somebody thinking out loud. `sale` and
  `done` only.
- **A cancelled order** is a customer who changed their mind.
- **Two lines of the same product on one order** is one customer, not two. The
  pairs are counted over DISTINCT orders - and over **templates**, so two
  lengths of the same track count once, which since the catalogue merge is the
  common case.
- **A delivery charge or a down payment** is on more orders than anything in
  the shop and belongs under nothing. Services are out, and so is anything
  unpublished - which excludes the plastic filler by the same rule that makes
  it unpublished in the first place.

### Beyond the four families

His four families were an answer about cones, cables, tracks and trims. His
order book also knows about rollers, hinges and drums, and **those are the ones
nobody would have gone looking for**. They are not dropped for fitting no
family - since the pool became one row there is no family heading to drop them
from, which is a second reason the single pool is the better shape.

### Setting them, per kit

> Sales (or Inventory) → Products → open the kit → **Sales** tab →
> **Upsell & Cross-Sell** → **Alternative Products**

The group is called *Upsell & Cross-Sell*, not eCommerce - an earlier version
of this file said eCommerce and sent the owner looking for a section that does
not exist. The tab is hidden altogether unless the product has **Can be Sold**
ticked, which is the other reason it can look missing.

**There is only one box in that group now.** It shipped with three that all
look like the same question - Alternative, Accessory and Optional Products -
and the owner had the other two hidden (2026-10-27): *"we only want the
alternative products choice."* Alternative is also the right one on its own
merits: Odoo's help for it says those products "show up on the product page",
which is where these go. Accessory feeds the cart; Optional feeds a quotation.
Hidden, not deleted - whatever is in them is still there and still works for
anything that reads it. `views/product_views.xml` is the whole of it.

Whatever is listed there is what appears under that product, in the order the
field holds them, capped by *Add-ons to show*. Nothing has to be said about
which heading anything belongs under, because there are no headings.

That field is Odoo's own and holds **product templates**, so one entry covers
a track with all twenty of its length-and-colour combinations behind it.

## Tier 3: the families, as the last fallback

A kit nobody has got to **and** nobody has bought twice shows the right
**kinds** - here are the cables, here are the tracks - rather than an empty
space. Never blank, never wrong, just less specific until either he or the
order book makes it specific.

The families are found by website category name: `Cones`, `Cables`, `Tracks`,
`Trims`. Where a catalogue calls them something else, point at the right one:

> Website → Configuration → Settings → **Garage Door Add-ons**

Those settings only affect the family fallback. **A product with its own
Alternative Products set ignores them entirely**, and so does one the counting
has an answer for.

### The fallback is for an EMPTY field, not for an empty result

A kit with one accessory set that happens to be unpublished has still been got
to. Falling back there would answer one deliberate choice with every cable in
the catalogue, so it does not: an empty field falls back, a field with
anything in it does not. A test holds that down, because it was wrong the
first time.

## Cones on the spring page

The calculator prices the cone set for the chosen I.D. into the spring itself,
at cost - so a customer configuring a spring **is already buying cones**, and a
row of them underneath reads as something missing from the order.

Asked whether to drop them, the owner said to keep them and say so: *"show
them but make it obvious that the cones are included so customers dont make
the mistake of buying when they dont need one."* So the spring page carries
the note and a kit page does not, because on a kit it would be a lie.

It used to hang off the Cones heading. With one pool it sits under the section
and appears only when a cone is actually in what is being shown - asked by
category **or by name**, because his live catalogue has no Cones category at
all and a warning that never appears is worse than one that turns up beside a
cone wrench.

## What shows a block

| | how it is recognised |
|---|---|
| a kit | the **website category** set in Settings, **or** the words *hardware kit* in its name, its product category or any of its website categories, **or** a part number beginning `HK-` |
| the spring | it is `spring_engineering.product_custom_spring` |
| anything else | nothing - a row of add-ons under every hinge in the shop is noise |

### This was wrong, and it made the whole feature invisible

Owner, 2026-10-27: *"i dont see the recommended products under the kits, and
yes i did put the categories in the garage door add-ons in the settings."*

It shipped looking for an `HK-<series>-<panels>P` part number, because that is
what `garage_door_supply/hooks.py` creates. **His shop does not sell those.**
The live catalogue has four kits - `AA-1200`, `AA-1600`, `AA-1800` and
`AA-Custom` - sitting in the **website** category *Hardware Kits*, and not one
of them carries an `HK-` code. So nothing was read as a kit, every page drew
nothing, and no amount of setting the four family categories could have helped.

The same crawl found that **three of the four families do not exist as
categories on his site at all**: it has Drums, EBF, Hardware Kits, Hinges,
Misc, Motors, Nuts & Bolts, Rollers, Shafts, Springs and Tracks. Only *Tracks*
matched. So the family lookup no longer insists on the exact name - it tries
the exact name, then the word (*Cables* finds *Lift Cables*), then the singular
(*Trims* finds *Trim Molding*) - and the setting remains the last word for a
category sharing no word at all.

**A product that says "Hardware Kit" in its name is a hardware kit.** Refusing
to read the name and demanding a part number instead was the mistake.

## Why don't I see them

> Website → Configuration → **Add-ons Check**

One line per product that gets a block, saying **what its page will draw and
where it came from** - "Cables 3, Tracks 8 (from your orders)", or "No block -
not read as a kit", or "Nothing to show - no add-on categories were found".

This exists because answering *"i dont see the recommended products under the
kits"* meant crawling the live website to discover that his kits are not shaped
the way this module assumed. That is not a way to answer the same question
twice.

## Notes for whoever changes this

- **Templates are shown, not variants.** A track is one product with twenty
  length-and-colour combinations behind it since the catalogue merge, so
  listing variants would put twenty near-identical cards under a kit. One card
  leads to the page where the choice is made.
- **This is deliberately not in `garage_door_supply`.** That module owns the
  homepage view and every update of it puts the shipped hero back over
  whatever has been done in the website builder.
- The block sits after `#product_full_description`, which is the last thing
  the standard page puts below the product before the builder's own drop zone.
- `_aa_addon_price` is best effort: a price that cannot be worked out is left
  off rather than shown as zero, which would read as free.
- **Raw SQL has to `flush_all()` first.** The counting is a self-join over
  every order line and is far too slow through the ORM, but SQL reads the
  database and not the ORM's pending writes - six tests failed on an order
  confirmed a moment earlier still sitting in the cache.
- **The pairs table is replaced, not topped up.** A pair that has stopped
  selling together should stop being recommended; a table that only grows
  recommends last spring's track for ever.
- **Only kits and the spring are counted for**, because nothing would ever
  read the other fifteen hundred products' pairs.
- `models.Constraint`, not `_sql_constraints` - the old attribute is ignored
  with a warning in Odoo 19.
