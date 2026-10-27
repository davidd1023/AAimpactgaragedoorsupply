# Pickup slots

A pickup day and time, chosen at checkout, carried through to the Work Order
sheet and the Dispatch list.

Owner, 2026-10-27: *"At checkout, the customer picks a pickup day and time
window, and it shows on the Work Order and in Dispatch. Done when: the chosen
slot appears on the order and the Dispatch list. (Our lead time is 2 labor
days, after those 2 days they choose when to pick up)."*

## The three answers this is built on

Asked, because each one changes what gets built:

**The lead time starts the next working day and takes two whole ones.** An
order placed **Monday** is collectable from **Thursday**; one placed **Friday**
starts Monday and is collectable **Wednesday**. The day the order is placed
never counts - an order placed at ten to five has had none of it.

**Any half hour from 7:00 AM to 4:00 PM.** He first chose two-hour windows,
then revised it the same day: *"the customer should be able to choose anytime
between 7 and 4, but dont make it a dropdown find some other option to make it
look good and let them choose a larger range of time."* So the time is stored
as an **hour of the day** - 7.0, 7.5, 16.0 - rather than one of four codes,
and the open hours are a setting, because a number that has moved once will
move again.

**Pickup orders only, and required.** Anything being delivered is never asked.
Anything being collected cannot be paid for without a slot, so nothing reaches
Dispatch blank for somebody to chase by telephone.

## Which delivery methods count as pickup

A checkbox, **"Collected in person"**, on the delivery method:

> Inventory → Configuration → Delivery Methods → open one

It is ticked once at install for anything that already reads as a collection -
`in_store` type, or a name containing *pickup*, *pick up* or *collect* - and is
yours to change after that. **There is no name matching at runtime**: a rule
that cannot be turned off is worse than a box somebody ticks, because the day
"Pickup rate for freight" is added it would start demanding slots with no way
to say no.

## Where the slot appears

| where | what shows |
|---|---|
| Checkout | a **calendar** for the day and a **grid of times**, under the delivery methods, only when collecting |
| Sales order form | **Pickup**, beside the delivery date |
| Sales order list | a **Pickup** column |
| Work Order sheet | a **Pickup** row in the WHEN block, in red like the deadline |
| Dispatch / transfers list | a **Pickup** column that is always there, plus **Pickup Day** for sorting |
| Transfers filters | *Collected today*, *Being collected*, and group by **Pickup Day** |

### The Dispatch column is NOT optional, and that is deliberate

Owner, 2026-10-27: *"i dont see the scheduled pickup date on the dispatch
screen, it showed up in manufacturing but not in dispatch."*

It was there - as an `optional="show"` column, which is only shown to somebody
who has **never touched that list's column chooser**. Anyone who has keeps the
set they saved, and a column added to the module afterwards arrives **hidden**
behind the little toggle at the right-hand end of the header. He has: this list
carries Dispatched, the work-station badges and the rest.

A column nobody can find is a column that is not there. The day somebody is
driving over to collect their order is not a display preference, so **Pickup**
has no `optional` at all. `Pickup Day`, the raw date, stays optional - it is
there for sorting, because the label reads "Fri 30 Oct" and sorts Friday before
Monday.

### Why the transfer stores its own copy, and how it is kept true

The Dispatch list is a list of transfers, and the first thing anybody wants to
do with a pickup time is **sort by it** - who is coming this morning. A related
field reaching through `sale_id` cannot be ordered on in the database, so the
day and window are **written onto the transfers**.

A stored copy written once goes stale, and the first cut wrote it once, at
confirmation. That left two holes:

- **A backorder carried nothing.** Odoo makes one by copying the transfer, and
  these fields are `copy=False` - rightly, so duplicating an order does not
  inherit somebody else's collection day. But a backorder is the same order's
  remaining half, and it is what the customer actually comes back for. It
  showed a blank Pickup column. `stock.picking.create` now fills it from the
  sale order whenever it is not given.
- **A slot moved after confirmation stayed on the old day.** Somebody
  telephones to say Friday instead; Dispatch went on reading Thursday off the
  screen while the sale order said otherwise, which is worse than no column.
  `sale.order.write` now pushes the change down.

Transfers already **done or cancelled are left alone**: what was on the
paperwork when it went out of the door is a record, not a field to tidy up.
The `19.0.2.1.0` migration fills in any transfer standing open whose order has
a slot, so the backorders already out there come right without anybody having
to touch the order again.

## Days the counter is shut

> Website → Configuration → Settings → **Pickup Slots** → Days closed for
> pickup

Comma-separated, as `2026-12-25, 2026-12-26`. They are neither counted towards
the two working days nor offered to a customer. A date somebody mistypes is
ignored rather than raising - a checkout that 500s over a fat-fingered holiday
is a worse fault than a day staying open.

## The two controls

**The day is a pop-up calendar**, not a list of dates (owner, 2026-10-27).
It is drawn in the browser from the days the server says are allowed - sent
down as `data-days` - so **a square that can be clicked is a day that will be
accepted**. There is one list, so the two cannot drift apart. Weekends,
closed days and anything inside the lead time are greyed and unclickable, and
the month arrows stop at the months that actually hold a selectable day
rather than letting somebody page into an empty grid for ever.

**The time is a grid of buttons**, not a dropdown. Nineteen half hours wrap
into a block that reads at a glance; a dropdown that long is a scroll.

## Nothing can be confirmed without both

Owner, 2026-10-27: *"the customer needs to pick a date and time before they
can confirm their order, currently they dont need to do either to proceed."*
He was right, and the reason is worth knowing:

**`_check_cart_is_ready_to_be_paid` is only reached on the zero-total path**
in Odoo 19. A pickup order with something to pay walked straight past it. The
hook the payment page actually consults is **`_get_shop_payment_errors`**, and
that is what `/shop/payment/validate` raises on. Both are overridden now.

The checkout button is also disabled until both are answered - both of them,
since there is one for mobile and one for desktop. That is a courtesy, not
the lock: being told at the payment step that you should have answered a
question two pages ago is no way to buy anything.

## Notes for whoever changes this

- **The day is checked twice**, in the controller as the customer chooses and
  again at the payment gate, both through `_aa_pickup_problem`. A select box is
  a suggestion, not a constraint; anyone can post that route a Sunday.
- **`_check_cart_is_ready_to_be_paid` is the only place that can enforce it.**
  The checkout page can be skipped, reloaded or posted to directly.
- **The checkout block is always rendered and hidden with a class.** Odoo swaps
  delivery methods without reloading, so a block only rendered when a pickup
  was already chosen would never appear for somebody who picks one afterwards.
- `website_sale_collect` - Odoo's own click-and-collect - is deliberately not
  used. It is not installed, and installing it would reshape the checkout with
  store selection and per-store stock for a question a checkbox answers.
