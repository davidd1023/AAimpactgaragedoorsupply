# The button on the door calculator

The calculator lives in a **different repository** -
`andy0808al/garage-door-calculator`, served by GitHub Pages - so its change
cannot be committed here. `send-to-manufacturing.patch` is that change, kept
beside the endpoint it talks to so the two halves can be read together.

## Applying it

```sh
git clone https://github.com/andy0808al/garage-door-calculator
cd garage-door-calculator
git apply /path/to/send-to-manufacturing.patch
git commit -am "Add a Send to Manufacturing button"
git push
```

It touches `index.html` only, adds 44 lines and removes none.

Then open the calculator, press the gear, and put the Odoo address under
**Odoo Address** - e.g. `https://aaigd.com`. It is stored in that browser's
local storage, so each person sets it once per device. Nothing else needs
configuring on the calculator side.

## What the button sends

The **door**, and nothing about products:

```json
{
  "wo": "W-1001", "mark": "A",
  "width": 108, "height": 84,
  "track": "3-15R", "lift": "standard", "hilift": 0,
  "sections": 4,
  "vertical": 76, "horizontal": 96,
  "weight": 300,
  "cable": 123, "cable_type": "Cable 5/32\"", "drum": "D400-144"
}
```

URL-encoded into `GET /door-work-order/new?spec=...`, which **creates nothing**
- it shows the cut list and asks. The POST behind that page's button is what
raises the order.

THE OMISSION IS THE DESIGN. No product id, no price, no quantity of anything
purchasable. Which stock item a length is cut from is decided in Odoo from
configuration, so a public page cannot name a product to be booked out of
stock, and a stale copy of the calculator cannot send a part number that has
since been retired. `test_the_sender_cannot_choose_a_product` holds that line.

`weight` is allowed to be null. The calculator cannot work out cables without
it and says so on its own screen, so a door sent without a weight becomes a
tracks-only order rather than a refusal or a guessed cable.

## Why a review page rather than one click

Two reasons, both learned the hard way elsewhere in this repository:

1. A link that creates records can be triggered by anything that can make a
   logged-in employee's browser fetch a URL. A GET that changes nothing cannot.
2. A mistyped door should be read by somebody before it becomes a job on the
   floor. The page prints every length in inches and eighths, the way the shop
   floor measures, so a wrong figure looks wrong.

A door sent twice does not become two doors: an unfinished order carrying the
same W/O and mark is reopened instead. That only works if the W/O field is
filled, which is why the button asks for confirmation when it is empty.
