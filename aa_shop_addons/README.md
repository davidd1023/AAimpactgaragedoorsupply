# Shop add-ons

The parts a customer still needs, shown under the kit or the spring they are
looking at. Owner, 2026-10-27: *"On every kit and spring page, show the
matching add-ons (cones, cables, tracks, trims) below the product. Done when:
each kit shows its correct add-ons."*

## Who decides what is "correct"

**He does.** A hardware kit knows its series and its panel count and nothing
else. What picks one cable out of twelve is the door height and the drum; what
picks one track is the height, the track size and the colour. None of those
live on the kit, so any rule the code invented would be confidently wrong.

Asked, the owner chose to set them himself, so the list is **Odoo's own
Accessory Products field** - right by definition, because he set it.

### Setting them, per kit

> Sales (or Inventory) → Products → open the kit → **Sales** tab →
> **Upsell & Cross-Sell** → **Accessory Products**

The group is called *Upsell & Cross-Sell*, not eCommerce - an earlier version
of this file said eCommerce and sent the owner looking for a section that does
not exist. The tab is hidden altogether unless the product has **Can be Sold**
ticked, which is the other reason it can look missing.

Twelve kits, `HK-1200-4P` through `HK-1800-7P`. Whatever is listed there is
what appears under that kit, **grouped automatically** by the website category
each product is already in - so adding a cable never also means saying it
belongs under "Cables".

That field is Odoo's own, so the products also appear as suggested accessories
in the cart. That is a bonus, not a side effect to undo.

## The fallback

A kit nobody has got to yet shows the right **kinds** - here are the cables,
here are the tracks - rather than an empty space. Never blank, never wrong,
just less specific until somebody makes it specific.

The families are found by website category name: `Cones`, `Cables`, `Tracks`,
`Trims`. Where a catalogue calls them something else, point at the right one:

> Website → Configuration → Settings → **Garage Door Add-ons**

Those settings only affect the fallback. **A product with its own Accessory
Products set ignores them entirely.**

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

## What shows a block

| | how it is recognised |
|---|---|
| a kit | part number begins `HK-`, **or** its product category says Hardware Kit |
| the spring | it is `spring_engineering.product_custom_spring` |
| anything else | nothing - a row of add-ons under every hinge in the shop is noise |

Two marks for a kit rather than one, because a kit added by hand later may well
not follow the SKU.

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
