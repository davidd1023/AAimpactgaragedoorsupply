# The button on the door calculator

The calculator lives in a **different repository** -
`andy0808al/garage-door-calculator`, served by GitHub Pages - so its change
cannot be committed here. `send-to-manufacturing.patch` is that change, kept
beside the endpoint it talks to so the two halves can be read together.

## Two forms of the same change

- **`index.html`** - the finished file. Download it and upload it over
  `index.html` in the calculator repository. This is the one to use.
- **`send-to-manufacturing.patch`** - the same change as a diff, 65 lines
  added and none removed. For reading what changed, or for `git apply` if
  you would rather not replace the whole file.

**It was built on commit `6f4c9d730388eef56299877e01c10d9821b9c65f` of `index.html`.** If that file has been
edited since, uploading this one would discard those edits - apply the patch
instead, or tell me and I will rebase it. `index-sandbox.html` and
`backup.html` are untouched.

Nothing was removed and no existing function was altered: the change adds a
button, a settings field for the Odoo address, and four functions.

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

## The Odoo address field

Paste **any page of your Odoo** - the Manufacturing page, the shop, the
dashboard. Only the scheme, host and port are kept; the path is discarded. A
bare `aaigd.com` works too and is assumed to be https.

This is not politeness, it is a fix. The field first took the address
literally, and the obvious thing to paste in a box used by "Send to
Manufacturing" is the Manufacturing page's own URL - which produced
`.../odoo/manufacturing/door-work-order/new`. Odoo's back end ignores the tail
of a path it does not recognise and renders the Manufacturing page, so the
button went somewhere plausible, raised nothing, and reported no error.

The settings panel now prints the address it will actually use, so a wrong one
is visible before it is relied on rather than after.

## Which build is running

The settings panel and the button both show a build number - currently
**build 3**. This page is delivered by uploading a file and has no cache
busting of its own, so a tab left open on the shop floor can keep running an
older copy for as long as it stays open, and "it still does the same thing" is
then indistinguishable from a real fault. The marker makes that answerable by
looking at the screen.

If the button does not say `b3`, the browser is running an older copy: reload
with a new query string (`?v=p3`) or hard-reload (Ctrl-Shift-R, Cmd-Shift-R).

The button also logs the exact address it is about to open to the browser
console, and says so if a pop-up blocker stopped the new tab.
